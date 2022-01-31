#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io
import os
import warnings
import argparse
from PIL import Image
from glob import glob
from math import ceil
import multiprocessing
from requests import session
import concurrent.futures as cf
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException


class Book:
    """Holder styr på all info om bildefiler til bok/avis/mm."""

    def __init__(self, digimedie):
        if digimedie.find("pliktmonografi") > -1:
            self.media_type = "pliktmonografi"
        else:
            self.media_type = "dig" + digimedie.split("dig")[1].split("_")[0]
        self.media_id = digimedie.split(self.media_type + "_")[1]
        self.current_page = "0001"
        self.max_threads = multiprocessing.cpu_count() * 4
        self.covers = False
        self.verbose = False
        self.print_url = False
        self.print_error = False
        self.tile_width = 1024
        self.tile_height = 1024
        self.api_url = "https://api.nb.no/catalog/v1/iiif/URN:NBN:no-nb"
        self.tilgang = ""
        self.image_url = ""
        self.folder_path = ""
        self.existing_images = []
        self.page_names = []
        self.page_data = {}
        self.page_url = {}
        self.num_pages = 0
        self.resize = 0
        self.session = session()
        self.session.headers["User-Agent"] = "Mozilla/5.0"
        self.adapter = HTTPAdapter(max_retries=(Retry(total=5, backoff_factor=0.5)))
        self.session.mount("https://", self.adapter)
        self.session.mount("http://", self.adapter)
        self.set_folder_path("." + os.path.sep + str(self.media_id) + os.path.sep)
        self.get_manifest()

    def set_tile_sizes(self, width, height):
        self.tile_width = width
        self.tile_height = height

    def set_to_print_url(self):
        self.print_url = True

    def set_to_print_errors(self):
        self.print_error = True

    def verbose_print(self):
        self.verbose = True

    def set_folder_path(self, folder_path):
        self.folder_path = folder_path
        self.find_existing_files()

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
        manifest_url = f"{self.api_url}_{self.media_type}" f"_{self.media_id}/manifest"
        try:
            response = self.session.get(manifest_url)
            response.raise_for_status()
            json_data = response.json()
        except RequestException as error:
            print(error)
        else:
            for page in json_data["sequences"][0]["canvases"]:
                if self.media_type == "digavis":
                    page_name = page["@id"].split("_")[-2]
                elif self.media_type == "digikart":
                    page_name = (
                        page["@id"].split("_")[-2] + "_" + page["@id"].split("_")[-1]
                    )
                else:
                    page_name = page["@id"].split("_")[-1]
                page_dims = [page["width"], page["height"]]
                if page_name.isdecimal():
                    self.page_names.append(page_name)
                self.page_data[page_name] = page_dims
                self.page_url[page_name] = page["images"][0]["resource"]["service"][
                    "@id"
                ]
            self.tilgang = json_data["metadata"][0]["value"]
            self.page_names = sorted(self.page_names)
            self.num_pages = len(self.page_names)

    def fetch_new_image_url(self, side, column, row):
        self.current_page = str(side)
        self.image_url = (
            f"{self.page_url[side]}/"
            f"{int(column)*self.tile_width},"
            f"{int(row)*self.tile_height},"
            f"{self.tile_width},{self.tile_height}"
            f"/full/0/native.jpg"
        )
        if self.print_url:
            print(self.image_url)
        return self.image_url

    def update_column_row(self, side):
        column_number, row_number = 0, 0
        if self.media_type == "digibok" or self.media_type == "digitidsskrift":
            self.set_tile_sizes(1024, 1024)
        else:
            self.set_tile_sizes(4096, 4096)
        column_number = ceil(self.page_data[side][0] / self.tile_width) - 1
        row_number = ceil(self.page_data[side][1] / self.tile_height) - 1
        return (int(column_number), int(row_number))

    def download_covers(self):
        self.covers = True

    def download(self):
        try:
            os.stat(self.folder_path)
        except OSError:
            os.mkdir(self.folder_path)
        imagelist = self.page_names
        if self.covers:
            for cover in ["I3", "I1", "C3", "C2", "C1"]:
                if cover in self.page_data:
                    imagelist = [cover, *imagelist]
        if self.existing_images:
            counter = 0
            for image in self.existing_images:
                if image in imagelist:
                    counter += 1
                    imagelist.remove(image)
            print(f"Hopper over {counter} eksisterende sider.")
        if len(imagelist) == 0:
            return False
        else:
            with cf.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
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
                                f"{' '*5}Lagrer side {progress} av {len(imagelist)}.",
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
                url = self.fetch_new_image_url(page_number, column_number, row_number)
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
                            ((column_number * part_width), (row_number * part_height)),
                        )
                        part_counter += 1
                        column_number += 1
                    row_number += 1
                if self.resize != 0:
                    full_page = full_page.resize(
                        [int(self.resize * s) for s in full_page.size]
                    )
                full_page.save(f"{self.folder_path}{page_number}.jpg")
                if self.verbose:
                    print(f"{' '*5}Lagret side {page_number}.jpg")
                return True, 200
            else:
                print(f"Feilet å laste ned side {page_number}.jpg - prøver igjen.")
                self.download_page(page_number)

    def make_pdf(self):
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        imagelist = self.page_names
        if self.covers:
            if "C1" in self.page_data:
                imagelist = ["C1", *imagelist]
            if "C3" in self.page_data:
                imagelist = [*imagelist, "C3"]
        for image in imagelist:
            image_path = f"{self.folder_path}{image}.jpg"
            try:
                Image.open(image_path).save(
                    self.media_id + ".pdf", "PDF", resolution=100.0, append=True
                )
                print(f"{' '*5}{image}.jpg --> {self.media_id}.pdf", end="\r")
            except OSError:
                Image.open(image_path).save(
                    self.media_id + ".pdf", "PDF", resolution=100.0
                )
                print(f"{' '*5}{image}.jpg --> {self.media_id}.pdf", end="\r")
            except Exception:
                print(f"For store bildefiler til å lage PDF, beklager.")
                return False
            if self.verbose:
                print("")
        return True


def f2pdf(image_location, pdf_name):
    try:
        Image.open(image_location).save(
            pdf_name + ".pdf", "PDF", resolution=100.0, append=True
        )
    except OSError:
        Image.open(image_location).save(pdf_name + ".pdf", "PDF", resolution=100.0)


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
    parser._action_groups.append(optional)
    args = parser.parse_args()

    if args.id:
        if args.f2pdf:
            media_type = "dig" + args.id.split("dig")[1].split("_")[0]
            media_id = str(args.id.split(media_type + "_")[1])
            filelist = []
            filelist.extend(glob(os.path.join(str(media_id), ("[0-9]" * 4) + ".jpg")))
            if not filelist:
                filelist.extend(
                    glob(os.path.join(str(media_id), ("[0-9]" * 3) + ".jpg"))
                )
            filelist = sorted(filelist)
            print(f"Lager {media_id}.pdf\n")
            if args.cover:
                filelist = [f"{media_id}/C1.jpg", *filelist, f"{media_id}/C3.jpg"]
            for file in filelist:
                f2pdf(file, str(media_id))
                print(
                    f"{' '*5}{file.split(os.path.sep)[1]} --> {media_id}.pdf", end="\r"
                )
                if args.v:
                    print("")
            print("\n\nFerdig med å lage pdf.")
            exit()
        book = Book(args.id)
        if args.url:
            book.set_to_print_url()
        if args.error:
            book.set_to_print_errors()
        if args.v:
            book.verbose_print()
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
        download = book.download()
        if download == False:
            print(
                f"\nNoe gikk galt, du prøvde å laste ned {book.media_type}, "
                f"med id {book.media_id}, er dette korrekt?"
            )
            exit()
        else:
            print(f"\n{' '*5}Ferdig med å laste ned alle sider.\n")
        if args.pdf:
            print(f"{' '*5}Lager {book.media_id}.pdf")
            savepdf = book.make_pdf()
            if savepdf:
                print(f"\n{' '*5}Ferdig med å lage pdf.\n")
        exit()
    else:
        parser.print_help()
        exit()


if __name__ == "__main__":
    main()
