# -*- coding: utf-8 -*-
import io
import os
import urllib.request
import urllib.error
import urllib.parse
import argparse
from PIL import Image
from glob import glob


class Book():
    """ Holder styr på all info om bildefiler til bok """
    def __init__(self, book_id):
        self.book_id = str(book_id)
        self.page_number = '0001'
        self.level = 5
        self.max_level = 5
        self.column_number = 0
        self.max_column = 0
        self.row_number = 0
        self.max_row = 0
        self.print_url = False
        self.print_error = False
        self.x_max_resolution = '9999'
        self.y_max_resolution = '9999'
        self.tile_width = '1024'
        self.tile_height = '1024'
        self.image_url = ''
        self.url_start_part = ''
        self.url_seperator1 = ''
        self.url_seperator2 = ''
        self.folder_path = ''

    def set_level(self, level):
        self.level = int(level)

    def set_max_level(self, max_level):
        self.max_level = int(max_level)

    def set_max_col(self, maxCol):
        self.max_column = int(maxCol)

    def set_max_row(self, maxRow):
        self.max_row = int(maxRow)

    def set_to_print_url(self):
        self.print_url = True

    def set_to_print_errors(self):
        self.print_error = True

    def set_folder_path(self, folder_path):
        self.folder_path = folder_path

    def update_url(self):
        self.image_url = (f'{self.url_start_part}'
                          f'{self.book_id}{self.url_seperator1}'
                          f'{self.page_number}{self.url_seperator2}'
                          f'&maxLevel={self.max_level}'
                          f'&level={self.level}'
                          f'&col={self.column_number}'
                          f'&row={self.row_number}'
                          f'&resX={self.x_max_resolution}'
                          f'&resY={self.y_max_resolution}'
                          f'&tileWidth={self.tile_width}'
                          f'&tileHeight={self.tile_height}')

    def set_book_or_newspaper(self, book_paper):
        if (book_paper == 'bok'):
            self.url_start_part = ('http://www.nb.no/services/image/resolver?'
                                   'url_ver=geneza&urn=URN:NBN:no-nb_digibok_')
            self.url_seperator1 = '_'
            self.url_seperator2 = ''
        elif (book_paper == 'avis'):
            self.url_start_part = ('http://www.nb.no/services/image/resolver?'
                                   'url_ver=geneza&urn=URN:NBN:no-nb_digavis_')
            self.url_seperator1 = '-1_'
            self.url_seperator2 = '_null'
        else:
            print('Feil type!')
            exit()

    def make_new_url(self, side, column, row):
        self.page_number = str(side)
        self.column_number = int(column)
        self.row_number = int(row)
        self.update_url()
        if self.print_url:
            print(self.image_url)
        return self.image_url

    def update_max_column_row(self, side):
        column_number, row_number = 0, 0
        while True:
            part_url = self.make_new_url(side, column_number, '0')
            try:
                req = urllib.request.Request(
                    part_url, headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(req)
            except urllib.error.HTTPError as error:
                column_number -= 1
                if self.print_error:
                    if error.code != 400:
                        print(error)
                break
            else:
                column_number += 1
        while True:
            part_url = self.make_new_url(side, '0', row_number)
            try:
                req = urllib.request.Request(
                    part_url, headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(req)
            except urllib.error.HTTPError as error:
                if self.print_error:
                    if error.code != 400:
                        print(error)
                row_number -= 1
                break
            else:
                row_number += 1
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
            url = book.make_new_url(page_number, column_number, row_number)
            try:
                req = urllib.request.Request(
                    url, headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(req).read()
            except urllib.error.HTTPError as error:
                if book.print_error:
                    print(error)
            else:
                try:
                    img = Image.open(io.BytesIO(response))
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
        part_width, part_height = image_parts[0].size
        full_page = Image.new('RGB', (max_width, max_height))
        row_number = 0
        part_counter = 0
        row_counter, column_counter = (row_counter - 1), (column_counter - 1)
        while (row_number <= row_counter):
            column_number = 0
            while (column_number <= column_counter):
                full_page.paste(
                    image_parts[part_counter],
                    ((column_number * part_width), (row_number * part_height)))
                part_counter += 1
                column_number += 1
            row_number += 1
        full_page.save(f'{book.folder_path}{page_number}.jpg')
        print(f'Lagret side {page_number}.jpg')


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
    optional.add_argument(
        '--level', metavar='<int>',
        help='Sett Level',
        default=False)
    optional.add_argument(
        '--maxlevel', metavar='<int>',
        help='Sett MaxLevel',
        default=False)
    optional.add_argument(
        '--maxcol', metavar='<int>',
        help='Sett MaxCol',
        default=False)
    optional.add_argument(
        '--maxrow', metavar='<int>',
        help='Sett MaxRow',
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
        if args.stop:
            stop_at_page = int(args.stop)
        else:
            stop_at_page = 9999
        if args.url:
            book.set_to_print_url()
        if args.error:
            book.set_to_print_errors()
        if args.level:
            book.set_level(int(args.level))
        if args.maxlevel:
            book.set_max_level(int(args.maxlevel))
        try:
            os.stat(book.folder_path)
        except OSError as e:
            os.mkdir(book.folder_path)
        if args.avis:
            book.set_book_or_newspaper('avis')
            print(f'Laster ned avis med ID: {args.id}')
            book.update_max_column_row(str(page_counter).rjust(3, '0'))
        else:
            book.set_book_or_newspaper('bok')
            print(f'Laster ned bok med ID: {args.id}')
            if args.cover:
                for cover in ['C1', 'C2', 'C3']:
                    book.update_max_column_row(cover)
                    download_page(cover, book)
                if args.pdf:
                    save_pdf(f'{book.folder_path}C1.jpg', str(args.id))
            book.update_max_column_row(str(page_counter).rjust(4, '0'))
        if args.maxcol:
            book.set_max_col(int(args.maxcol))
        if args.maxrow:
            book.set_max_row(int(args.maxrow))
        while True:
            if args.avis:
                download = download_page(str(page_counter).rjust(3, '0'), book)
            else:
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
