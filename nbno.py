#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io
import os
import re
import warnings
import argparse
import threading
from PIL import Image, UnidentifiedImageError
from glob import glob
from math import ceil
import multiprocessing
from requests import session
import concurrent.futures as cf
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException


BASE_DIR = os.environ.get('DOWNLOAD_DIR', '.')
# directory for aggregated PDFs
# PDFs and sources organized per book directory

class Book:
    """Holder styr på all info om bildefiler til bok/avis/mm."""

    def __init__(self, digimedie, cli_mode=False):
        # original passed ID; media_type and media_id will be set next
        self.digimedie = digimedie
        # run in CLI mode (flat dirs) vs. webapp mode (sources/, metadata/, pdf/)
        self.cli_mode = bool(cli_mode)
        if digimedie.find("plikt") > -1:
            self.media_type = "plikt" + \
                digimedie.split("plikt")[1].split("_")[0]
        else:
            self.media_type = "dig" + digimedie.split("dig")[1].split("_")[0]
        self.media_id = digimedie.split(self.media_type + "_")[1]
        # default folder_name = type + '_' + id
        self.folder_name = f"{self.media_type}_{self.media_id}"
        # store the original download folder name for canonical references
        self.default_folder_name = self.folder_name
        self.current_page = "0001"
        self.max_workers = multiprocessing.cpu_count() * 4
        self.covers = False
        self.verbose = False
        self.print_url = False
        self.print_error = False
        self.tile_width = 1024
        self.tile_height = 1024
        self.api_url = "https://api.nb.no/catalog/v1/iiif/URN:NBN:no-nb"
        self.tilgang = ""
        self.image_url = ""
        self.title = "nbnopy"
        self.folder_path = ""
        self.existing_images = []
        self.page_names = []
        self.raw_metadata = []
        self.page_data = {}
        self.page_url = {}
        self.num_pages = 0
        # manifest-level thumbnail (from IIIF manifest), if any
        self.manifest_thumbnail = None
        self.resize = 0
        self.session = session()
        self.session.headers["User-Agent"] = "Mozilla/5.0"
        self.adapter = HTTPAdapter(max_retries=(
            Retry(total=5, backoff_factor=0.5)))
        self.session.mount("https://", self.adapter)
        self.session.mount("http://", self.adapter)
        # whether to include a cover page (C1.jpg) first in PDF output
        self.include_cover = False
        # base output directory may be configured via DOWNLOAD_DIR env var
        self.set_folder_path(os.path.join(BASE_DIR, self.folder_name) + os.path.sep)
        # per-book storage layout differs: flat (CLI) or nested (webapp)
        if self.cli_mode:
            self.sources_dir = self.folder_path
            self.pdf_dir = self.folder_path
            self.meta_dir = self.folder_path
        else:
            self.sources_dir = os.path.join(self.folder_path, 'sources') + os.path.sep
            self.pdf_dir = os.path.join(self.folder_path, 'pdf') + os.path.sep
            self.meta_dir = os.path.join(self.folder_path, 'metadata') + os.path.sep
        self.get_manifest()
        self.image_lock = threading.Lock()
        self.download_skipped = False
        self._pdf_redownload_attempts = set()

    def set_tile_sizes(self, width, height):
        self.tile_width = width
        self.tile_height = height

    def _extract_label_text(self, label):
        if isinstance(label, str):
            return label
        if isinstance(label, list):
            for entry in label:
                text = self._extract_label_text(entry)
                if text:
                    return text
        if isinstance(label, dict):
            for entry in label.values():
                text = self._extract_label_text(entry)
                if text:
                    return text
        return ""

    def set_to_print_url(self):
        self.print_url = True

    def set_to_print_errors(self):
        self.print_error = True

    def set_title(self):
        # rename folder to title string
        self.folder_name = self.title
        self.set_folder_path(os.path.join(BASE_DIR, self.folder_name) + os.path.sep)

    def set_folder_name(self, folder_name):
        """Override the target folder/pdf name before downloading."""
        self.folder_name = folder_name
        self.set_folder_path(os.path.join(BASE_DIR, self.folder_name) + os.path.sep)

    def verbose_print(self):
        self.verbose = True

    def set_folder_path(self, folder_path):
        self.folder_path = folder_path
        self.find_existing_files()

    def load_cookie(self, file_path):
        with open(file_path) as f:
            for line in f:
                if "=" in line:
                    key, value = map(str.strip, line.split("=", 1))
                    if key in ["authorization", "cookie"]:
                        self.session.headers[key] = value
        if self.verbose:
            print(self.session.headers)

    def find_existing_files(self):
        filelist = []
        filelist.extend(glob(os.path.join(f"{self.folder_path}*.jpg")))
        if filelist:
            for file in filelist:
                self.existing_images.extend(
                    [file.split(".jpg")[0].split(os.path.sep)[2]]
                )

    def set_resize(self, size):
        self.resize = int(size) / 100

    def set_from_page(self, frompage):
        pages = []
        for page in self.page_names:
            if int(page) >= frompage:
                pages.append(page)
        self.page_names = pages

    def set_to_page(self, topage):
        pages = []
        for page in self.page_names:
            if int(page) <= topage:
                pages.append(page)
        self.page_names = pages

    def get_manifest(self):
        manifest_url = f"{self.api_url}_{self.media_type}_{self.media_id}/manifest"
        try:
            response = self.session.get(manifest_url)
            response.raise_for_status()
            json_data = response.json()
        except RequestException as error:
            print(error)
            return
        # retain raw metadata for preview
        self.raw_metadata = json_data.get('metadata', [])
        # grab manifest-level thumbnail if provided
        thumb_val = json_data.get('thumbnail')
        if thumb_val:
            # thumbnail may be dict or list
            if isinstance(thumb_val, list) and thumb_val:
                t = thumb_val[0]
            else:
                t = thumb_val
            # IIIF Presentation v3 uses 'id', v2 uses '@id'
            if isinstance(t, dict):
                self.manifest_thumbnail = t.get('id') or t.get('@id')
            elif isinstance(t, str):
                self.manifest_thumbnail = t
        metadata = self.raw_metadata or []
        if metadata:
            first_entry = metadata[0]
            tilgang_val = None
            if isinstance(first_entry, dict):
                tilgang_val = first_entry.get("value")
            elif isinstance(first_entry, str):
                tilgang_val = first_entry
            if tilgang_val:
                self.tilgang = tilgang_val
            label_candidate = self._extract_label_text(json_data.get("label"))
            if not label_candidate and len(metadata) > 1:
                second_entry = metadata[1]
                if isinstance(second_entry, dict):
                    label_candidate = second_entry.get("value", "")
                elif isinstance(second_entry, str):
                    label_candidate = second_entry
            if label_candidate:
                self.title = re.sub(r"[^\w_. -]", "", label_candidate)

        for page in json_data["sequences"][0]["canvases"]:
            if self.media_type == "digavis":
                page_name = page["@id"].split("_")[-2]
            elif self.media_type == "digikart":
                page_name = (
                    page["@id"].split("_")[-2] + "_" +
                    page["@id"].split("_")[-1]
                )
            else:
                page_name = page["@id"].split("_")[-1]
            page_dims = [page["width"], page["height"]]
            if page_name.isdecimal():
                self.page_names.append(page_name)
            self.page_data[page_name] = page_dims
            self.page_url[page_name] = page["images"][0]["resource"]["service"]["@id"]
        self.page_names = sorted(self.page_names)
        self.num_pages = len(self.page_names)

    def fetch_new_image_url(self, side, column, row):
        # compute region to request, clamped to page bounds to avoid oversize requests
        orig_w, orig_h = self.page_data[side]
        x = int(column) * self.tile_width
        y = int(row) * self.tile_height
        # clamp width/height for last tiles so as not to exceed page dimensions
        region_w = min(self.tile_width, orig_w - x)
        region_h = min(self.tile_height, orig_h - y)
        image_url = (
            f"{self.page_url[side]}/"
            f"{x},{y},{region_w},{region_h}"
            f"/full/0/native.jpg"
        )
        if self.print_url:
            print(f"Side: {side}, Col: {column}, Row: {row}")
            print(image_url)
        return image_url

    def update_column_row(self, side):
        column_number, row_number = 0, 0
        # use smaller tile sizes for 'plikt' resources to avoid access restrictions
        if self.media_type.startswith("plikt"):
            self.set_tile_sizes(300, 300)
        elif self.media_type in ("digibok", "digitidsskrift"):
            self.set_tile_sizes(1024, 1024)
        else:
            self.set_tile_sizes(4096, 4096)
        column_number = ceil(self.page_data[side][0] / self.tile_width) - 1
        row_number = ceil(self.page_data[side][1] / self.tile_height) - 1
        return (int(column_number), int(row_number))

    def download_covers(self):
        # include cover pages in download AND PDF ordering
        self.covers = True
        self.include_cover = True

    def set_include_cover(self, flag=True):
        """If True, put C1.jpg as first page in generated PDF."""
        self.include_cover = bool(flag)

    def download(self):
        # prepare directories: sources (images), metadata, pdf
        os.makedirs(self.sources_dir, exist_ok=True)
        os.makedirs(self.meta_dir, exist_ok=True)
        os.makedirs(self.pdf_dir, exist_ok=True)
        # record original ID and title metadata for UI gallery
        # write metadata for gallery
        # write metadata for gallery UI only in webapp mode
        if not self.cli_mode:
            try:
                with open(os.path.join(self.meta_dir, '.nbno_id'), 'w') as mf:
                    mf.write(self.digimedie)
                # use manifest thumbnail URL (IIIF) rather than local preview logic
                thumb = self.manifest_thumbnail
                import datetime, json
                meta = {
                    'orig': self.digimedie,
                    'title': self.title,
                    'type': self.media_type,
                    'pages': self.num_pages,
                    'thumbnail': thumb,
                    # use timezone-aware now() rather than deprecated utcnow()
                    'timestamp': int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
                }
                if hasattr(self, 'custom_title'):
                    meta['custom_title'] = self.custom_title
                with open(os.path.join(self.meta_dir, '.nbno_meta.json'), 'w', encoding='utf-8') as mf:
                    json.dump(meta, mf)
            except Exception:
                pass
        self.download_skipped = False
        imagelist = self.page_names
        if self.covers:
            # order covers same as GUI/web PDF: C1, I1, numbered pages, I3, C2, C3
            front = []
            back = []
            for cover in ("C1", "I1"):  # front covers
                if cover in self.page_data:
                    front.append(cover)
            # numeric pages (page_names are already sorted)
            numeric = [p for p in imagelist if p.isdecimal()]
            for cover in ("I3", "C2", "C3"):  # back covers
                if cover in self.page_data:
                    back.append(cover)
            imagelist = front + numeric + back
        if self.existing_images:
            counter = 0
            for image in self.existing_images:
                if image in imagelist:
                    counter += 1
                    imagelist.remove(image)
            print(f"{' '*5}Hopper over {counter} eksisterende sider.")
        if len(imagelist) == 0:
            if self.existing_images:
                print(f"{' '*5}Alle bildene finnes allerede lokalt; hopper over nedlasting.")
                self.download_skipped = True
                return True
            return False
        else:
            with cf.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_download = {
                    executor.submit(self.download_page, page): page
                    for page in imagelist
                }
                progress = 0
                print("")
                for future in cf.as_completed(future_download):
                    download = future.result()
                    if not download[0]:
                        if download[1] == 403:
                            print(f"HTTP 403 Forbidden: Får ikke tilgang til boken.")
                            print(f"Fra nb.nb   -   {self.tilgang}.")
                        elif download[1] == 408:
                            print(f"Connection Timeout ved forsøk på å laste sider.")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    else:
                        progress += 1
                        if not self.verbose:
                            print(
                                f"{' ' * 5}Lagrer side {progress} av {len(imagelist)}.",
                                end="\r",
                            )
            if self.verbose:
                print(f"\n{' '*5}Lagrer side {progress} av {len(imagelist)}.")
            return download[0]

    def download_page(self, page_number):
        """Laster ned og setter sammen bildedeler for side av boken"""
        max_column, max_row = self.update_column_row(page_number)
        image_parts = []
        max_width, max_height = 0, 0
        row_counter, column_counter = 0, 0
        row_number = 0
        HTTPerror = 0
        while row_number <= max_row:
            column_number = 0
            while column_number <= max_column:
                url = self.fetch_new_image_url(
                    page_number, column_number, row_number)
                try:
                    response = self.session.get(url, timeout=10)
                    response.raise_for_status()
                except RequestException as error:
                    try:
                        response
                    except:
                        HTTPerror = 408
                        break
                    else:
                        if response.status_code == 403:
                            HTTPerror = 403
                            break
                    if self.print_error:
                        print(error)
                else:
                    try:
                        img = Image.open(io.BytesIO(response.content))
                        with self.image_lock:
                            image_parts.append(img)
                        if row_number == 0:
                            max_width += img.size[0]
                            column_counter += 1
                        if column_number == 0:
                            max_height += img.size[1]
                            row_counter += 1
                    except IOError as error:
                        if self.print_error:
                            print(error)
                column_number += 1
            row_number += 1
            if HTTPerror != 0:
                break
        if HTTPerror == 403:
            return False, 403
        elif HTTPerror == 408:
            return False, 408
        elif not len(image_parts):
            return False, 200
        else:
            if len(image_parts) == (column_number * row_number):
                part_width, part_height = image_parts[0].size
                full_page = Image.new("RGB", (max_width, max_height))
                row_number = 0
                part_counter = 0
                row_counter = row_counter - 1
                column_counter = column_counter - 1
                while row_number <= row_counter:
                    column_number = 0
                    while column_number <= column_counter:
                        full_page.paste(
                            image_parts[part_counter],
                            ((column_number * part_width),
                             (row_number * part_height)),
                        )
                        part_counter += 1
                        column_number += 1
                    row_number += 1
                if self.resize != 0:
                    full_page = full_page.resize(
                        [int(self.resize * s) for s in full_page.size]
                    )
                full_page.save(os.path.join(self.sources_dir, f"{page_number}.jpg"))
                if self.verbose:
                    print(f"{' '*5}Lagret side {page_number}.jpg")
                return True, 200
            else:
                if page_number in ["I3", "I1", "C3", "C2", "C1"]:
                    print(f"Feilet å laste ned side {page_number}.jpg - hopper over.")
                    return True, 200
                else:
                    print(f"Feilet å laste ned side {page_number}.jpg - prøver igjen.")
                    return self.download_page(page_number)

    def _attempt_redownload_page_for_pdf(self, path):
        page_name = os.path.splitext(os.path.basename(path))[0]
        if page_name in self._pdf_redownload_attempts:
            return False
        self._pdf_redownload_attempts.add(page_name)
        try:
            os.remove(path)
        except OSError:
            pass
        print(
            f"{' '*5}Korrupt bildefil oppdaget for {page_name} under PDF-generering; "
            "sletter og laster inn siden på nytt."
        )
        success, status = self.download_page(page_name)
        if not success:
            print(
                f"Kunne ikke laste ned {page_name} på nytt (HTTP {status}); "
                "PDF-generering avbrytes."
            )
        return success

    def _open_pdf_image(self, path):
        try:
            return Image.open(path)
        except (UnidentifiedImageError, IOError) as error:
            if self.print_error:
                print(error)
            if self._attempt_redownload_page_for_pdf(path):
                try:
                    return Image.open(path)
                except (UnidentifiedImageError, IOError) as second_error:
                    if self.print_error:
                        print(second_error)
            return None

    def make_pdf(self):
        """Build a PDF from all downloaded JPGs in the folder."""
        # filter out any warnings for large images
        warnings.simplefilter("error", Image.DecompressionBombWarning)

        # list all .jpg files in sources subdir (and optionally include cover first)
        pattern = os.path.join(self.sources_dir, "*.jpg")
        files = sorted(glob(pattern))
        if self.include_cover:
            # desired order: C1, I1, numbered pages, I3, C2, C3
            basenames = [os.path.basename(f) for f in files]
            lower = [b.lower() for b in basenames]
            ordered = []
            # front covers
            for name in ('c1.jpg', 'i1.jpg'):
                if name in lower:
                    idx = lower.index(name)
                    ordered.append(files[idx])
            # numeric pages
            for fpath, bname in zip(files, basenames):
                if bname[:-4].isdigit():
                    ordered.append(fpath)
            # back covers
            for name in ('i3.jpg', 'c2.jpg', 'c3.jpg'):
                if name in lower:
                    idx = lower.index(name)
                    ordered.append(files[idx])
            # append any remaining pages
            for fpath in files:
                if fpath not in ordered:
                    ordered.append(fpath)
            files = ordered
        if not files:
            print("No images found to build PDF.")
            return False

        # name PDF after the folder_name, not the original ID
        # ensure PDF_DIR exists
        # ensure per-book pdf directory exists
        os.makedirs(self.pdf_dir, exist_ok=True)
        output_pdf = os.path.join(self.pdf_dir, f"{self.folder_name}.pdf")
        # try efficient PDF assembly via img2pdf to reduce peak memory use
        try:
            import img2pdf

            with open(output_pdf, "wb") as f:
                f.write(img2pdf.convert(files))
            print(f"PDF created: {output_pdf}")
            return True
        except ImportError:
            pass
        except Exception as e:
            print(f"Error creating PDF via img2pdf: {e}")
            print("Falling back to PIL for PDF creation.")

        # fallback to PIL-based assembly (may use more memory)
        self._pdf_redownload_attempts.clear()
        try:
            images = []
            for path in files:
                image = self._open_pdf_image(path)
                if image is None:
                    return False
                images.append(image)
            images[0].save(
                output_pdf,
                "PDF",
                resolution=100.0,
                save_all=True,
                append_images=images[1:]
            )
            print(f"PDF created: {output_pdf}")
            return True
        except Exception as e:
            print(f"Error creating PDF: {e}")
            return False


def f2pdf(image_location, pdf_name):
    try:
        Image.open(image_location).save(
            pdf_name + ".pdf", "PDF", resolution=100.0, append=True
        )
    except OSError:
        Image.open(image_location).save(
            pdf_name + ".pdf", "PDF", resolution=100.0)


def main():
    parser = argparse.ArgumentParser()
    optional = parser._action_groups.pop()
    required = parser.add_argument_group("required arguments")
    required.add_argument(
        "--id",
        metavar="<bokID>",
        help="IDen på mediet som skal lastes ned",
        default=False,
    )
    optional.add_argument(
        "--cover", action="store_true", help="Settes for å laste covers", default=False
    )
    optional.add_argument(
        "--title",
        action="store_true",
        help="Settes for å hente tittel på bok automatisk",
        default=False,
    )
    optional.add_argument(
        "--pdf",
        action="store_true",
        help="Settes for å lage pdf av bildene som lastes",
        default=False,
    )
    optional.add_argument(
        "--f2pdf",
        action="store_true",
        help="Settes for å lage pdf av bilder i eksisterende mappe",
        default=False,
    )
    optional.add_argument(
        "--url",
        action="store_true",
        help="Settes for å printe URL av hver del",
        default=False,
    )
    optional.add_argument(
        "--error",
        action="store_true",
        help="Settes for å printe feilkoder",
        default=False,
    )
    optional.add_argument(
        "--v",
        action="store_true",
        help="Settes for å printe mer info",
        default=False,
    )
    optional.add_argument(
        "--resize",
        metavar="<int>",
        help="Prosent av originalstørrelse på bilder",
        default=False,
    )
    optional.add_argument(
        "--start", metavar="<int>", help="Sidetall å starte på", default=False
    )
    optional.add_argument(
        "--stop", metavar="<int>", help="Sidetall å stoppe på", default=False
    )
    optional.add_argument(
        "--cookie",
        metavar="<string>",
        help="Sti til fil for autentisering",
        default=False
    )
    parser._action_groups.append(optional)
    args = parser.parse_args()

    if args.id:
        if args.f2pdf:
            media_type = "dig" + args.id.split("dig")[1].split("_")[0]
            media_id = str(args.id.split(media_type + "_")[1])
            filelist = []
            filelist.extend(
                glob(os.path.join(str(media_id), ("[0-9]" * 4) + ".jpg")))
            if not filelist:
                filelist.extend(
                    glob(os.path.join(str(media_id), ("[0-9]" * 3) + ".jpg"))
                )
            filelist = sorted(filelist)
            print(f"\nLager {media_id}.pdf\n")
            if args.cover:
                filelist = [f"{media_id}/C1.jpg",
                            *filelist, f"{media_id}/C3.jpg"]
            for file in filelist:
                f2pdf(file, str(media_id))
                print(
                    f"{' '*5}{file.split(os.path.sep)[1]} --> {media_id}.pdf", end="\r"
                )
                if args.v:
                    print("")
            print("\n\nFerdig med å lage pdf.")
            exit()
        # CLI mode: flat directory structure for direct downloads
        book = Book(args.id, cli_mode=True)
        if args.url:
            book.set_to_print_url()
        if args.error:
            book.set_to_print_errors()
        if args.v:
            book.verbose_print()
        if args.cookie:
            if os.path.exists(args.cookie):
                book.load_cookie(args.cookie)
            else:
                print(f"Fil for autentisering ikke funnet: {args.cookie}")
                exit()
        if args.resize:
            book.set_resize(int(args.resize))
        if args.start:
            book.set_from_page(int(args.start))
        if args.stop:
            book.set_to_page(int(args.stop))
            if int(args.stop) > book.num_pages:
                print("Du har forsøkt å laste ned flere sider enn det eksisterer.")
                print(
                    f"Det finnes kun {book.num_pages} sider, du får ikke flere enn dette."
                )
        print(f"Laster ned {book.media_type} med ID: {book.media_id}.")
        if args.cover:
            book.download_covers()
        if args.title:
            book.set_title()
        download = book.download()
        if download == False:
            print(
                f"\nNoe gikk galt, du prøvde å laste ned {book.media_type}, "
                f"med id {book.media_id}, er dette korrekt?"
            )
            exit()
        else:
            if not book.download_skipped:
                print(f"\n{' '*5}Ferdig med å laste ned alle sider.\n")
        if args.pdf:
            print(f"\nLager {book.media_id}.pdf")
            savepdf = book.make_pdf()
            if savepdf:
                print(f"\n{' '*5}Ferdig med å lage pdf.\n")
        exit()
    else:
        parser.print_help()
        exit()


if __name__ == "__main__":
    main()
