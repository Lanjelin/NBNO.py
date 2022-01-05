# -*- coding: utf-8 -*-
import io
import os
import warnings
import argparse
import requests
from PIL import Image
from glob import glob
from math import ceil


class Book():
    """ Holder styr på all info om bildefiler til bok/avis/mm. """
    def __init__(self, book_id):
        self.book_id = str(book_id)
        self.media_type = ''
        self.current_page = '0001'
        self.print_url = False
        self.print_error = False
        self.tile_width = 1024
        self.tile_height = 1024
        self.api_url = 'https://api.nb.no/catalog/v1/iiif/URN:NBN:no-nb'
        self.image_url = ''
        self.folder_path = ''
        self.page_names = []
        self.page_data = {}
        self.page_url = {}
        self.num_pages = 0
        self.session = requests.session()
        self.session.headers['User-Agent'] = 'Mozilla/5.0'

    def set_tile_sizes(self, width, height):
        self.tile_width = width
        self.tile_height = height

    def set_media_type(self, media_type):
        self.media_type = media_type

    def set_to_print_url(self):
        self.print_url = True

    def set_to_print_errors(self):
        self.print_error = True

    def set_folder_path(self, folder_path):
        self.folder_path = folder_path

    def get_manifest(self):
        manifest_url = (f'{self.api_url}_{self.media_type}'
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
                if (self.media_type == 'digavis'):
                    page_name = page['@id'].split('_')[-2]
                elif (self.media_type == 'digikart'):
                    page_name = page['@id'].split('_')[-2] + '_' + \
                                page['@id'].split('_')[-1]
                else:
                    page_name = page['@id'].split('_')[-1]
                page_dims = [page["width"], page["height"]]
                self.page_names.append(page_name)
                self.page_data[page_name] = page_dims
                self.page_url[page_name] = page['images'][0]['resource']\
                                               ['service']['@id']
            if (self.media_type == 'digibok'):
                self.num_pages = len(self.page_data) - 5
            else:
                self.num_pages = len(self.page_data)

    def fetch_new_image_url(self, side, column, row):
        self.current_page = str(side)
        self.image_url = (f'{self.page_url[side]}/'
                          f'{int(column)*self.tile_width},'
                          f'{int(row)*self.tile_height},'
                          f'{self.tile_width},{self.tile_height}'
                          f'/full/0/native.jpg')
        if self.print_url:
            print(self.image_url)
        return self.image_url

    def update_column_row(self, side):
        column_number, row_number = 0, 0
        if self.media_type == 'digibok' or self.media_type == 'digitidsskrift':
            self.set_tile_sizes(1024, 1024)
        else:
            self.set_tile_sizes(4096, 4096)
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
        help='IDen på mediet som skal lastes ned',
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
        help='Settes for å lage pdf av bilder i eksisterende mappe',
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
        media_type = 'dig'+args.id.split('dig')[1].split('_')[0]
        media_id = str(args.id.split(media_type+'_')[1])
        book = Book(media_id)
        book.set_media_type(media_type)
        book.set_folder_path('.'+os.path.sep+str(media_id)+os.path.sep)
        if args.f2pdf:
            filelist = []
            filelist.extend(
                glob(os.path.join(str(media_id), ('[0-9]'*4)+'.jpg')))
            filelist = sorted(filelist)
            print(f'Lager {media_id}.pdf')
            if args.cover:
                save_pdf(
                    f'{book.folder_path}C1.jpg', str(media_id))
                print(f'{media_id}{os.path.sep}C1.jpg --> {media_id}.pdf')
            for file in filelist:
                save_pdf(file, str(media_id))
                print(f'{file} --> {media_id}.pdf')
            print('Ferdig med å lage pdf.')
            exit()
        if args.pdf:
            make_pdf = True
        else:
            make_pdf = False
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
        book.get_manifest()
        if args.stop:
            stop_at_page = int(args.stop)
        else:
            stop_at_page = book.num_pages
        if page_counter > stop_at_page:
            print('Du har forsøkt å laste ned flere sider enn det eksisterer.')
            print(f'Det finnes kun {book.num_pages} sider i denne boka.')
            exit()
        print(f'Laster ned {media_type} med ID: {media_id}.')
        while True:
            if media_type == 'digavis' or \
               media_type == 'digikart' or \
               media_type == 'digifoto' or \
               media_type == 'digimanus' or \
               media_type == 'digitidsskrift':
                book.update_column_row(book.page_names[page_counter-1])
                download = download_page(book.page_names[page_counter-1], book)
            elif media_type == 'digibok' or \
                 media_type == 'digiprogramrapport':
                if args.cover:
                    for cover in ['C1', 'C2', 'C3']:
                        book.update_column_row(cover)
                        download_page(cover, book)
                    if args.pdf:
                        save_pdf(f'{book.folder_path}C1.jpg', str(media_id))
                book.update_column_row(str(page_counter).rjust(4, '0'))
                download = download_page(str(page_counter).rjust(4, '0'), book)
            else:
                print(f'Noe gikk galt, du prøvde å laste ned {media_type}, '
                      f'med id {media_id}, er dette korrekt?')
            if download is False:
                break
            if make_pdf:
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                try:
                    save_pdf(
                        f'{book.folder_path}'
                        f'{book.current_page}.jpg', str(media_id))
                except Exception as e:
                    print(f'For store bildefiler til å lage PDF, beklager.')
                    make_pdf = False
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
