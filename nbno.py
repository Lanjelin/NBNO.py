# -*- coding: utf-8 -*-
import io
import os
import argparse
import requests
from PIL import Image
from glob import glob
from math import ceil


class Book():
    """ Holder styr på all info om bildefiler til bok """
    def __init__(self, book_id):
        self.book_id = str(book_id)
        self.book_paper = ''
        self.page_number = '0001'
        self.column_number = 0
        self.row_number = 0
        self.print_url = False
        self.print_error = False
        self.tile_width = 1024
        self.tile_height = 1024
        self.api_url = 'https://api.nb.no/catalog/v1/iiif/URN:NBN:no-nb'
        self.image_url = ''
        self.resolver_url = ''
        self.url_seperator1 = ''
        self.url_seperator2 = ''
        self.folder_path = ''
        self.page_data = {}
        self.num_pages = 0
        self.session = requests.session()
        self.session.headers['User-Agent'] = 'Mozilla/5.0'

    def set_tile_sizes(self, width, height):
        self.tile_width = width
        self.tile_height = height

    def set_book_or_newspaper(self, book_paper):
        self.book_paper = book_paper

    def set_to_print_url(self):
        self.print_url = True

    def set_to_print_errors(self):
        self.print_error = True

    def set_folder_path(self, folder_path):
        self.folder_path = folder_path

    def get_url_seperators(self):
        if (self.book_paper == 'digibok'):
            self.url_seperator1 = '_'
            self.url_seperator2 = ''
        elif (self.book_paper == 'digavis'):
            url_seperators1 = ['-1_', '-01_']
            url_seperators2 = ['_null', '_seksjonsnavn']
            for sep1, sep2 in zip(url_seperators1, url_seperators2):
                json_url = (f'{self.resolver_url}_'
                            f'{self.book_paper}_{self.book_id}'
                            f'{sep1}001{sep2}/info.json')
                try:
                    response = self.session.get(manifest_url)
                    response.raise_for_status()
                except requests.exceptions.RequestException as error:
                    if self.print_error:
                        if error.response.status_code != 400:
                            print(error)
                else:
                    self.url_seperator1 = sep1
                    self.url_seperator2 = sep2
                    break

    def get_manifest(self):
        manifest_url = (f'{self.api_url}_{self.book_paper}'
                        f'_{self.book_id}/manifest')
        try:
            response = self.session.get(manifest_url)
            response.raise_for_status()
            json_data = response.json()
        except requests.exceptions.RequestException as error:
            if self.print_error:
                print(error)
        else:
            for page in json_data['sequences'][0]['canvases']:
                if (self.book_paper == 'digibok'):
                    page_name = page['@id'].split('_')[-1]
                elif (self.book_paper == 'digavis'):
                    page_name = page['@id'].split('_')[-2]
                page_dims = [page["width"], page["height"]]
                self.page_data[page_name] = page_dims
            if (self.book_paper == 'digibok'):
                self.num_pages = len(self.page_data) - 5
            elif (self.book_paper == 'digavis'):
                self.num_pages = len(self.page_data)
            self.resolver_url = json_data["thumbnail"]["@id"].split("_")[0]

    def update_image_url(self):
        self.image_url = (f'{self.resolver_url}_{self.book_paper}_'
                          f'{self.book_id}{self.url_seperator1}'
                          f'{self.page_number}{self.url_seperator2}/'
                          f'{self.column_number*self.tile_width},'
                          f'{self.row_number*self.tile_height},'
                          f'{self.tile_width},{self.tile_height}'
                          f'/full/0/native.jpg')
        if self.print_url:
            print(self.image_url)

    def fetch_new_image_url(self, side, column, row):
        self.page_number = str(side)
        self.column_number = int(column)
        self.row_number = int(row)
        self.update_image_url()
        return self.image_url

    def update_column_row(self, side):
        column_number, row_number = 0, 0
        if self.book_paper == 'digavis':
            self.set_tile_sizes(self.page_data[side][0],
                                self.page_data[side][1])
        column_number = (ceil(self.page_data[side][0] / self.tile_width) - 1)
        row_number = (ceil(self.page_data[side][1] / self.tile_height) - 1)
        self.max_column = int(column_number)
        self.max_row = int(row_number)


def download_page(page_number, book):
    """ Laster ned og setter sammen bildedeler for side av boken """
    image_parts = []
    max_width, max_height = 0, 0
    row_counter, column_counter = 0, 0
    row_number = 0
    while (row_number <= book.max_row):
        column_number = 0
        while (column_number <= book.max_column):
            url = book.fetch_new_image_url(page_number,
                                           column_number,
                                           row_number)
            try:
                response = book.session.get(url)
                response.raise_for_status()
            except requests.exceptions.RequestException as error:
                if book.print_error:
                    print(error)
            else:
                try:
                    img = Image.open(io.BytesIO(response.content))
                    image_parts.append(img)
                    if (row_number == 0):
                        max_width += img.size[0]
                        column_counter += 1
                    if (column_number == 0):
                        max_height += img.size[1]
                        row_counter += 1
                except IOError as error:
                    if book.print_error:
                        print(error)
            column_number += 1
        row_number += 1
    if not len(image_parts):
        print('Ferdig med å laste ned alle sider.')
        return False
    else:
        if (len(image_parts) == (column_number*row_number)):
            part_width, part_height = image_parts[0].size
            full_page = Image.new('RGB', (max_width, max_height))
            row_number = 0
            part_counter = 0
            row_counter = (row_counter - 1)
            column_counter = (column_counter - 1)
            while (row_number <= row_counter):
                column_number = 0
                while (column_number <= column_counter):
                    full_page.paste(
                        image_parts[part_counter],
                        ((column_number * part_width),
                         (row_number * part_height)))
                    part_counter += 1
                    column_number += 1
                row_number += 1
            full_page.save(f'{book.folder_path}{page_number}.jpg')
            print(f'Lagret side {page_number}.jpg')
        else:
            print(f'Feilet å laste ned side {page_number}.jpg - prøver igjen.')
            download_page(page_number, book)


def save_pdf(image_location, pdf_name):
    try:
        Image.open(image_location).save(
            pdf_name+'.pdf', 'PDF', resolution=100.0, append=True)
    except OSError:
        Image.open(image_location).save(
            pdf_name+'.pdf', 'PDF', resolution=100.0)


def main():
    parser = argparse.ArgumentParser()
    optional = parser._action_groups.pop()
    required = parser.add_argument_group('required arguments')
    required.add_argument(
        '--id', metavar='<bokID>',
        help='IDen på boken som skal lastes ned',
        default=False)
    optional.add_argument(
        '--avis', action='store_true',
        help='Settes om det er en avis som lastes',
        default=False)
    optional.add_argument(
        '--cover', action='store_true',
        help='Settes for å laste covers',
        default=False)
    optional.add_argument(
        '--pdf', action='store_true',
        help='Settes for å lage pdf av bildene som lastes',
        default=False)
    optional.add_argument(
        '--f2pdf', action='store_true',
        help='Settes for å lage pdf av bilder i mappe',
        default=False)
    optional.add_argument(
        '--url', action='store_true',
        help='Settes for å printe URL av hver del',
        default=False)
    optional.add_argument(
        '--error', action='store_true',
        help='Settes for å printe feilkoder',
        default=False)
    optional.add_argument(
        '--start', metavar='<int>',
        help='Sidetall å starte på',
        default=False)
    optional.add_argument(
        '--stop', metavar='<int>',
        help='Sidetall å stoppe på',
        default=False)
    parser._action_groups.append(optional)
    args = parser.parse_args()

    if args.id:
        book = Book(str(args.id))
        book.set_folder_path('.'+os.path.sep+str(args.id)+os.path.sep)
        if args.f2pdf:
            filelist = []
            filelist.extend(
                glob(os.path.join(str(args.id), ('[0-9]'*4)+'.jpg')))
            filelist = sorted(filelist)
            print(f'Lager {args.id}.pdf')
            if args.cover:
                save_pdf(
                    f'{book.folder_path}C1.jpg', str(args.id))
                print(f'{args.id}{os.path.sep}C1.jpg --> {args.id}.pdf')
            for file in filelist:
                save_pdf(file, str(args.id))
                print(f'{file} --> {args.id}.pdf')
            print('Ferdig med å lage pdf.')
            exit()
        if args.start:
            page_counter = int(args.start)
        else:
            page_counter = 1
        if args.url:
            book.set_to_print_url()
        if args.error:
            book.set_to_print_errors()
        try:
            os.stat(book.folder_path)
        except OSError:
            os.mkdir(book.folder_path)
        if args.avis:
            book.set_book_or_newspaper('digavis')
            book.get_manifest()
            book.get_url_seperators()
            print(f'Laster ned avis med ID: {args.id}.')
        else:
            book.set_book_or_newspaper('digibok')
            book.get_manifest()
            book.get_url_seperators()
            print(f'Laster ned bok med ID: {args.id}.')
            if args.cover:
                for cover in ['C1', 'C2', 'C3']:
                    book.update_column_row(cover)
                    download_page(cover, book)
                if args.pdf:
                    save_pdf(f'{book.folder_path}C1.jpg', str(args.id))
        if args.stop:
            stop_at_page = int(args.stop)
        else:
            stop_at_page = book.num_pages
        if page_counter > stop_at_page:
            print('Du har forsøkt å laste ned flere sider enn det eksisterer.')
            print(f'Det finnes kun {book.num_pages} sider i denne boka.')
            exit()
        while True:
            if args.avis:
                book.update_column_row(str(page_counter).rjust(3, '0'))
                download = download_page(str(page_counter).rjust(3, '0'), book)
            else:
                book.update_column_row(str(page_counter).rjust(4, '0'))
                download = download_page(str(page_counter).rjust(4, '0'), book)
            if download is False:
                break
            if args.pdf:
                save_pdf(
                    f'{book.folder_path}{book.page_number}.jpg', str(args.id))
            if (page_counter == stop_at_page):
                print('Ferdig med å laste ned alle sider.')
                break
            page_counter += 1
        exit()
    else:
        parser.print_help()
        exit()


if __name__ == '__main__':
    main()
