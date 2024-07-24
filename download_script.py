#!/usr/bin/env python

import requests
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
import subprocess
from argparse import ArgumentParser
from multiprocessing import Pool

def download_html(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Check if the request was successful
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None


class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture_data = False
        self.target_class = ""
        self.captured_data = []
        self.file_ids = []

    # def handle_starttag(self, tag, attrs):
    #     if tag == "span":
    #         for attr in attrs:
    #             if attr[0] == "class" and attr[1] == self.target_class:
    #                 self.capture_data = True

    # def handle_endtag(self, tag):
    #     if tag == "span" and self.capture_data:
    #         self.capture_data = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            for attr in attrs:
                if attr[0] == self.target_class:
                    print(attr[0], attr[1])
                    self.file_ids.append(attr[1])
                    self.capture_data = True

    def handle_endtag(self, tag):
        if tag == "tr" and self.capture_data:
            self.capture_data = False

    def handle_data(self, data):
        if self.capture_data:
            self.captured_data.append(data)

    # def extract_span_by_class(self, html, class_value):
    #     self.target_class = class_value
    #     self.captured_data = []
    #     self.feed(html)
    #     # return self.captured_data
    #     return self.file_ids

    def extract_tr_by_attr(self, html):
        self.target_class = "data-id"
        self.captured_data = []
        self.feed(html)
        # return self.captured_data
        return self.file_ids




def handle_args():
    p = ArgumentParser(description="Download files from AARNet FileSender URL. By default will download 8 files concurrently.", 
    usage="""download_script.py [-h] --url URL [--parallel PARALLEL] [--single {tar,zip}]
       (url string should be enclosed in quotation marks)""")
    p.add_argument("--url", "-u", required=True, help="URL to FileSender download page, url string should be enclosed in quotation marks")
    p.add_argument("--parallel", "-p", type=int, default=8, help="Number of files to download in parallel (default behaviour), default=8")
    p.add_argument("--outdir", "-o", default="./", help="Output directory")
    p.add_argument("--single", "-s", choices=["tar", "zip"], 
                   help="Download data in a single archive file (either zip or tar). If specified, overrides --parallel")
    return p.parse_args()

OUTDIR="./"
def download_url(url):
    print(f"downloading {url}")
    wget_cmd = f"wget -P {OUTDIR} --content-disposition \"{url}\""
    wget_proc = subprocess.Popen(wget_cmd, shell=True)
    wget_proc.communicate()

class FileSenderDownload:
    def __init__(self, url, archive_format=None):
        self.archive_format = archive_format
        self.html_content = download_html(url)
        parser = MyHTMLParser()

        self.token = url.split("&token=")[1]
        print(self.token)

#        self.directlinks = parser.extract_span_by_class(self.html_content, "directlink")
#        self.directlinks = [x.split("Direct Link: ")[1].strip() for x in self.directlinks]
#        self.fileids = [x.split("&files_ids=")[1] for x in self.directlinks]
        self.fileids = parser.extract_tr_by_attr(self.html_content)
        baseurl = "https://filesender.aarnet.edu.au/download.php"
        print(self.fileids)
        self.directlinks = [ f"{baseurl}?token={self.token}&files_ids={x}" for x in self.fileids ]
        print(self.directlinks)

    def single_archive_link(self):
        base_url = "https://filesender.aarnet.edu.au/download.php?"
        base_url += f"token={self.token}&files_ids={'%2C'.join(self.fileids)}&archive_format={self.archive_format}"
        return base_url

if __name__=="__main__":
    args = handle_args()
    OUTDIR=args.outdir

    fsdownload=FileSenderDownload(args.url, archive_format=args.single)
    if args.single:
        print(f"downloading a single {args.single} file")
        download_url(fsdownload.single_archive_link())
        exit()
    elif args.parallel:
        print(f"download {args.parallel} files in parallel")
        if args.parallel < 1:
            raise ValueError("--parallel value must be positive integer")
        elif args.parallel == 1:
            for url_ in fsdownload.directlinks:
                download_url(url_)
        else:
            pool = Pool(args.parallel)
            pool.map(download_url, fsdownload.directlinks)
        





# https://filesender.aarnet.edu.au/download.php?token=d6be9395-9fc6-427f-b565-289cb32a16e2&files_ids=22322589%2C22322355%2C22322460%2C22322286%2C22322646%2C22322397%2C22322496%2C22322271%2C22322595%2C22322385%2C22322676%2C22322358%2C22322547%2C22322253%2C22322661%2C22322340%2C22322640%2C22322313%2C22322685%2C22322361%2C22322619%2C22322301%2C22322631%2C22322319%2C22322190%2C22322136%2C22322127%2C22322124%2C22322265%2C22322196%2C22322217%2C22322163%2C22322229%2C22322157%2C22322205%2C22322148%2C22322199%2C22322145%2C22322247%2C22322184%2C22322232%2C22322166%2C22322244%2C22322175%2C22322322%2C22322250%2C22322220%2C22322169%2C22322379%2C22322316%2C22322292%2C22322226%2C22322574%2C22322406%2C22322505%2C22322388%2C22322562%2C22322400%2C22322610%2C22322454%2C22322613%2C22322481%2C22322529%2C22322442%2C22322553%2C22322448%2C22322541%2C22322472%2C22322568%2C22322520%2C22322478%2C22322433%2C22322469%2C22322331%2C22322304%2C22322238%2C22322367%2C22322259%2C22322376%2C22322295%2C22322268%2C22322193%2C22322283%2C22322208%2C22322370%2C22322274%2C22322256%2C22322181%2C22322334%2C22322223%2C22322463%2C22322307%2C22322415%2C22322280%2C22322364%2C22322262%2C22322424%2C22322277%2C22322142%2C22322130%2C22322298%2C22322211%2C22322235%2C22322172%2C22322325%2C22322241%2C22322289%2C22322214%2C22322160%2C22322133%2C22322178%2C22322154%2C22322373%2C22322337%2C22322202%2C22322187%2C22322151%2C22322139%2C22322592%2C22322538%2C22322487%2C22322403%2C22322571%2C22322475%2C22322604%2C22322502%2C22322625%2C22322577%2C22322682%2C22322532%2C22322679%2C22322535%2C22322583%2C22322421%2C22322664%2C22322511%2C22322673%2C22322526%2C22322655%2C22322445%2C22322607%2C22322412%2C22322634%2C22322439%2C22322499%2C22322310%2C22322517%2C22322328%2C22322556%2C22322346%2C22322550%2C22322352%2C22322598%2C22322394%2C22322667%2C22322484%2C22322616%2C22322409%2C22322628%2C22322430%2C22322652%2C22322457%2C22322565%2C22322343%2C22322586%2C22322391%2C22322580%2C22322382%2C22322559%2C22322349%2C22322643%2C22322466%2C22322637%2C22322436%2C22322601%2C22322418%2C22322691%2C22322508%2C22322697%2C22322544%2C22322649%2C22322451%2C22322658%2C22322490%2C22322688%2C22322523%2C22322694%2C22322514%2C22322622%2C22322427%2C22322670%2C22322493%2C22322121%2C22322700%2C22322703&archive_format=zip&transaction_id=ac97c143-344b-452b-a017-006fbaddac7e