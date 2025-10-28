#!/usr/bin/env python3
"""
Simple web interface for nbno downloader.
"""
import builtins
import io
import json
import os
import queue
import re
import subprocess
import threading
from datetime import datetime

import ocrmypdf
from flask import Flask, render_template, request, jsonify, Response, send_from_directory, send_file
from nbno import Book
import requests

# ensure only one PDF/OCR job runs at a time
pdf_lock = threading.Lock()

app = Flask(__name__)


@app.route('/', methods=['GET'])
def index():
    # list existing downloaded books (subdirs in DOWNLOAD_DIR)
    download_dir = os.environ.get('DOWNLOAD_DIR', '.')
    books = []
    # sort book directories by recorded download timestamp (descending)
    entries = [nm for nm in os.listdir(download_dir)
               if os.path.isdir(os.path.join(download_dir, nm)) and nm != 'logs']
    # load numeric timestamps (UNIX) or parse legacy ISO strings
    ts_map = {}
    for name in entries:
        mf = os.path.join(download_dir, name, 'metadata', '.nbno_meta.json')
        if os.path.isfile(mf):
            try:
                with open(mf, encoding='utf-8') as f:
                    ts = json.load(f).get('timestamp')
                if isinstance(ts, (int, float)):
                    ts_map[name] = ts
                elif isinstance(ts, str):
                    try:
                        ts_map[name] = int(datetime.fromisoformat(ts.rstrip('Z')).timestamp())
                    except Exception:
                        pass
            except Exception:
                pass
            # fallback to metadata file mtime
            if name not in ts_map:
                try:
                    ts_map[name] = os.path.getmtime(mf)
                except Exception:
                    pass
    # sort by timestamp (0 for missing), newest first
    entries.sort(key=lambda nm: ts_map.get(nm, 0), reverse=True)
    for name in entries:
        folder = os.path.join(download_dir, name)
        # load saved metadata: title, original ID, thumbnail, type, pages
        meta_file = os.path.join(folder, 'metadata', '.nbno_meta.json')
        display = name.replace('_', ' ')
        orig = name
        try:
            import json
            with open(meta_file, encoding='utf-8') as mf:
                meta = json.load(mf)
                orig = meta.get('orig', orig)
                display = meta.get('custom_title') or meta.get('title', display)
                thumb = meta.get('thumbnail')
                mtype = meta.get('type')
                pages = meta.get('pages')
                custom = meta.get('custom_title')
        except Exception:
            thumb = None
            mtype = None
            pages = None
            custom = None
        # pick C1.jpg if present, else fall back to first page 0001.jpg; else use metadata thumbnail
        sources_folder = os.path.join(folder, 'sources')
        cover_file = None
        # prefer front cover C1.jpg
        if os.path.exists(os.path.join(sources_folder, 'C1.jpg')):
            cover_file = 'C1.jpg'
        else:
            # fallback to first numeric page
            if os.path.exists(os.path.join(sources_folder, '0001.jpg')):
                cover_file = '0001.jpg'
        # detect existing pdf in pdf subfolder and compute size if present
        pdf_path = os.path.join(folder, 'pdf', f"{name}.pdf")
        has_pdf = os.path.exists(pdf_path)
        pdf_size = None
        if has_pdf:
            try:
                size = os.path.getsize(pdf_path)
                pdf_size = f"{round(size / (1024 * 1024))} MB"
            except Exception:
                pdf_size = None
        # choose cover URL: prefer local C1 or 0001 via ?w=500; fallback to metadata thumbnail
        cover_url = None
        if cover_file:
            cover_url = f'/files/{name}/sources/{cover_file}?w=500'
        elif thumb:
            cover_url = thumb
        books.append({
            'dir': name,
            'orig': orig,
            'title': display,
            'custom_title': custom,
            'type': mtype,
            'pages': pages,
            'cover': cover_url,
            'pdf_url': f'/files/{name}/pdf/{name}.pdf',
            'has_pdf': has_pdf,
            'pdf_size': pdf_size,
        })
    # detect available Tesseract languages via tesseract CLI
    ocrlangs = []
    try:
        res = subprocess.run(
            ['tesseract', '--list-langs'], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, check=True
        )
        for ln in res.stdout.splitlines():
            code = ln.strip()
            # skip header lines like 'List of available languages (', keep codes
            if code and not code.lower().startswith('list') and not code.startswith('---'):
                ocrlangs.append(code)
    except Exception:
        pass
    return render_template('index.html', books=books, ocrlangs=ocrlangs)


@app.route('/files/<path:subpath>')
def files(subpath):
    # serve downloaded image files or PDFs
    download_dir = os.environ.get('DOWNLOAD_DIR', '.')
    path = os.path.join(download_dir, subpath)
    if os.path.exists(path):
        # on-the-fly resizing for JPEGs via ?w=width parameter
        if subpath.lower().endswith('.jpg'):
            width = request.args.get('w', type=int)
            if width:
                try:
                    from PIL import Image

                    img = Image.open(path)
                    wpercent = width / float(img.size[0])
                    hsize = int(img.size[1] * wpercent)
                    img = img.resize((width, hsize), Image.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=85)
                    buf.seek(0)
                    return send_file(buf, mimetype='image/jpeg')
                except Exception:
                    pass
        return send_from_directory(download_dir, subpath)
    return ('Not found', 404)

@app.route('/make_pdf/<dirname>', methods=['GET', 'POST'])
def make_pdf(dirname):
    """Generate PDF for a downloaded book and optionally OCR via ocrmypdf."""
    # only one PDF/OCR job at a time
    if not pdf_lock.acquire(blocking=False):
        return jsonify({'error': 'En annen PDF-prosess kjører allerede'}), 409
    download_dir = os.environ.get('DOWNLOAD_DIR', '.')
    folder = os.path.join(download_dir, dirname)
    if not os.path.isdir(folder):
        return jsonify({'error': 'Folder not found'}), 404
    # load original ID from metadata
    orig = dirname
    meta_file = os.path.join(folder, 'metadata', '.nbno_meta.json')
    try:
        with open(meta_file, encoding='utf-8') as mf:
            meta = json.load(mf)
            orig = meta.get('orig', orig)
    except Exception:
        pass
    # OCR options and streaming flag
    raw_flags = request.args.get('flags', '').strip()
    ocr_flags = raw_flags.split() if raw_flags else []
    include_cover = request.args.get('include_cover') == 'true'
    stream = request.args.get('stream') == '1'
    # quick non-streaming mode (JSON response)
    if not stream:
        try:
            book = Book(orig)
            book.set_folder_name(dirname)
            if include_cover:
                book.set_include_cover(True)
            ok = book.make_pdf()
            if ok:
                # run the exact ocrmypdf CLI command as provided by the GUI
                pdf_path = os.path.join(download_dir, dirname, 'pdf', f"{dirname}.pdf")
                cmd = ['ocrmypdf', *ocr_flags, pdf_path, pdf_path]
                subprocess.run(cmd, check=True)
            return jsonify({'success': ok}) if ok else ('', 500)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            pdf_lock.release()
    # streaming SSE logs; also append to server-side log file
    records = queue.Queue()
    logs_dir = os.path.join(download_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, 'pdf_ocr.log')
    def hook_print(*args, **kwargs):
        msg = ' '.join(str(a) for a in args)
        # send to SSE queue
        records.put(msg)
        # append to persistent log file
        try:
            with open(log_file, 'a', encoding='utf-8') as lf:
                lf.write(msg + "\n")
        except Exception:
            pass

    old_print = builtins.print
    builtins.print = hook_print
    def worker():
        try:
            print(f"Building PDF for {dirname}...")
            book = Book(orig)
            book.set_folder_name(dirname)
            # honor GUI toggle for including cover as first page
            if include_cover:
                book.set_include_cover(True)
            book.make_pdf()
            # always run ocrmypdf to compress (and OCR if enabled)
            pdf_path = os.path.join(download_dir, dirname, 'pdf', f"{dirname}.pdf")
            # build ocrmypdf command exactly from user-provided flags
            cmd = ['ocrmypdf']
            if ocr_flags:
                cmd.extend(ocr_flags)
            cmd.extend([pdf_path, pdf_path])
            # DEBUG: show the ocrmypdf command in streaming worker
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                print(line.strip())
            proc.wait()
        except Exception:
            print("Error while building PDF:")
            import traceback

            traceback.print_exc()
        finally:
            builtins.print = old_print
            records.put(None)
            pdf_lock.release()

    threading.Thread(target=worker, daemon=True).start()
    def generate():
        while True:
            msg = records.get()
            if msg is None:
                yield 'event: done\ndata: {}\n\n'
                break
            payload = json.dumps({'msg': msg})
            yield f"event: log\ndata: {payload}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/pages/<dirname>', methods=['GET'])
def pages(dirname):
    """Return JSON list of source image filenames for browsing previews."""
    download_dir = os.environ.get('DOWNLOAD_DIR', '.')
    folder = os.path.join(download_dir, dirname)
    sources = os.path.join(folder, 'sources')
    if not os.path.isdir(sources):
        return jsonify([])
    imgs = sorted(f for f in os.listdir(sources) if f.lower().endswith('.jpg'))
    include_cover = request.args.get('include_cover') == 'true'
    if include_cover:
        # desired order: C1, I1, numbered pages, I3, C2, C3
        lower_imgs = [f.lower() for f in imgs]
        ordered = []
        for name in ('c1.jpg', 'i1.jpg'):
            if name in lower_imgs:
                idx = lower_imgs.index(name)
                ordered.append(imgs[idx])
                imgs.pop(idx)
                lower_imgs.pop(idx)
        # numeric pages
        numeric = [f for f in imgs if f[:-4].isdigit()]
        ordered.extend(numeric)
        imgs = [f for f in imgs if not f[:-4].isdigit()]
        lower_imgs = [f.lower() for f in imgs]
        for name in ('i3.jpg', 'c2.jpg', 'c3.jpg'):
            if name in lower_imgs:
                idx = lower_imgs.index(name)
                ordered.append(imgs[idx])
                imgs.pop(idx)
                lower_imgs.pop(idx)
        # append any remaining pages
        ordered.extend(imgs)
        imgs = ordered
    else:
        # if a front cover thumbnail named C1.jpg exists, show it first
        lower_imgs = [f.lower() for f in imgs]
        if 'c1.jpg' in lower_imgs:
            idx = lower_imgs.index('c1.jpg')
            imgs.insert(0, imgs.pop(idx))
    return jsonify(imgs)


@app.route('/delete/<bookname>', methods=['DELETE'])
def delete_book(bookname):
    import shutil
    download_dir = os.environ.get('DOWNLOAD_DIR', '.')
    folder = os.path.join(download_dir, bookname)
    try:
        shutil.rmtree(folder)
        return ('', 204)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logs/<path:subpath>', methods=['GET'])
def serve_logs(subpath):
    download_dir = os.environ.get('DOWNLOAD_DIR', '.')
    logs_dir = os.path.join(download_dir, 'logs')
    path = os.path.join(logs_dir, subpath)
    if os.path.exists(path):
        return send_from_directory(logs_dir, subpath)
    return ('', 200, {'Content-Type': 'text/plain'})


@app.route('/preview', methods=['GET'])
def preview():
    """Return metadata/thumbnails for a given media ID (used in queue preview)."""
    media_id = request.args.get('id', '').strip()
    if not media_id:
        return jsonify({'error': 'Missing id parameter'}), 400
    try:
        book = Book(media_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    thumb = None
    preview_page = None
    # try a C1 cover thumbnail first
    if 'C1' in book.page_url:
        c1_url = f"{book.page_url['C1']}/full/!200,200/0/native.jpg"
        try:
            import requests

            resp = requests.head(c1_url, timeout=5)
            if resp.status_code == 200:
                thumb = c1_url
                preview_page = 'C1'
        except Exception:
            pass
    # fallback to first numeric page thumbnail
    if not thumb and book.page_names:
        preview_page = book.page_names[0]
        thumb = f"{book.page_url[preview_page]}/full/!200,200/0/native.jpg"
    data = {
        'title': book.title,
        'type': book.media_type,
        'pages': book.num_pages,
        'preview_page': preview_page,
        'thumbnail': thumb,
        'access': book.tilgang,
        'metadata': book.raw_metadata,
    }
    return jsonify(data)




@app.route('/download', methods=['GET'])
def download():
    # collect parameters (supports comma-separated multiple IDs)
    raw_ids = request.args.get('id', '').strip()
    raw_names = request.args.get('name', '').strip()
    if not raw_ids:
        return "Missing id", 400
    media_ids = [m.strip() for m in re.split(r'[;,\s]+', raw_ids) if m.strip()]
    # split custom names on commas/semicolons only; preserve spaces within names
    media_names = [n.strip() for n in re.split(r'[;,]+', raw_names) if n.strip()]

    # gather options
    cover_flag = request.args.get('cover') == 'true'
    title_flag = request.args.get('title') == 'true'
    try:
        resize_val = int(request.args.get('resize'))
    except (TypeError, ValueError):
        resize_val = None
    try:
        start_val = int(request.args.get('start'))
    except (TypeError, ValueError):
        start_val = None
    try:
        stop_val = int(request.args.get('stop'))
    except (TypeError, ValueError):
        stop_val = None

    # setup persistent logging (download + OCR) via SSE & file
    records = queue.Queue()
    download_dir = os.environ.get('DOWNLOAD_DIR', '.')
    logs_dir = os.path.join(download_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, 'pdf_ocr.log')

    def hook_print(*args, **kwargs):
        msg = ' '.join(str(a) for a in args)
        # SSE
        records.put(msg)
        # append to persistent log
        try:
            with open(log_file, 'a', encoding='utf-8') as lf:
                lf.write(msg + "\n")
        except Exception:
            pass

    import builtins
    old_print = builtins.print
    builtins.print = hook_print

    def worker():
        try:
            for idx, mid in enumerate(media_ids):
                # allow custom title/folder name; replace whitespace with underscores
                raw_name = media_names[idx] if idx < len(media_names) else mid
                clean = re.sub(r"[^\w\s-]", "", raw_name)
                folder_name = re.sub(r"\s+", "_", clean)
                # instantiate and remember custom title for metadata
                book = Book(mid)
                book.set_folder_name(folder_name)
                book.custom_title = raw_name
                # show custom title (matches metadata) in banner
                print(f"\n=== Downloading {mid} - '{book.custom_title}' ===")
                if cover_flag:
                    book.download_covers()
                if title_flag:
                    book.set_title()
                if resize_val is not None:
                    book.set_resize(resize_val)
                if start_val is not None:
                    book.set_from_page(start_val)
                if stop_val is not None:
                    book.set_to_page(stop_val)
                book.download()
        finally:
            builtins.print = old_print
            records.put(None)

    threading.Thread(target=worker, daemon=True).start()

    prog_pattern = re.compile(r"side\s+(\d+)\s+av\s+(\d+)", re.IGNORECASE)

    def generate():
        while True:
            msg = records.get()
            if msg is None:
                yield 'event: done\ndata: {}\n\n'
                break
            m = prog_pattern.search(msg)
            if m:
                p, t = map(int, m.groups())
                payload = json.dumps({'page': p, 'total': t, 'msg': msg})
                yield f"event: progress\ndata: {payload}\n\n"
            else:
                payload = json.dumps({'msg': msg})
                yield f"event: log\ndata: {payload}\n\n"

    return Response(generate(), mimetype='text/event-stream')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
