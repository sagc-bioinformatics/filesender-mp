#!/usr/bin/env python3
#
# FileSender www.filesender.org
#
# Copyright (c) 2009-2019, AARNet, Belnet, HEAnet, SURFnet, UNINETT
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# *   Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
# *   Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
# *   Neither the name of AARNet, Belnet, HEAnet, SURFnet and UNINETT nor the
#     names of its contributors may be used to endorse or promote products
#     derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import argparse
try:
    import requests
    import time
    from collections.abc import Iterable
    from collections.abc import MutableMapping
    import hmac
    import hashlib
    import urllib3
    import os
    import json
    import configparser
    from os.path import expanduser
    from multiprocessing import Pool
    from functools import partial
    from string import Template
except Exception as e:
    print(type(e))
    print(e.args)
    print(e)
    print('')
    print('ERROR: A required dependency is not installed, please check your')
    print('distribution packages or run something like the following')
    print('')
    print('pip3 install requests urllib3 ')
    exit(1)

##########################################################################

def flatten(d, parent_key=''):
    items = []
    for k, v in d.items():
        new_key = parent_key + '[' + k + ']' if parent_key else k
        if isinstance(v, MutableMapping):
            items.extend(flatten(v, new_key).items())
        else:
            items.append(new_key+'='+v)
    items.sort()
    return items

def call(method, path, data, content=None, rawContent=None, options={}):
    data['remote_user'] = username
    data['timestamp'] = str(round(time.time()))
    flatdata = flatten(data)
    signed = bytes(method+'&'+base_url.replace('https://', '',
                   1).replace('http://', '', 1)+path+'?'+('&'.join(flatten(data))), 'ascii')
    content_type = options['Content-Type'] if 'Content-Type' in options else 'application/json'

    inputcontent = None
    if content is not None and content_type == 'application/json':
        inputcontent = json.dumps(content, separators=(',', ':'))
        signed += bytes('&'+inputcontent, 'ascii')
    elif rawContent is not None:
        inputcontent = rawContent
        signed += bytes('&', 'ascii')
        signed += inputcontent

    # print(signed)
    bkey = bytearray()
    bkey.extend(map(ord, apikey))
    data['signature'] = hmac.new(bkey, signed, hashlib.sha1).hexdigest()

    url = base_url+path+'?'+('&'.join(flatten(data)))
    headers = {
        "Accept": "application/json",
        "Content-Type": content_type
    }
    response = None
    if method == "get":
        response = requests.get(url, verify=not insecure, headers=headers)
    elif method == "post":
        response = requests.post(
            url, data=inputcontent, verify=not insecure, headers=headers)
    elif method == "put":
        response = requests.put(url, data=inputcontent,
                                verify=not insecure, headers=headers)
    elif method == "delete":
        response = requests.delete(url, verify=not insecure, headers=headers)

    if response is None:
        raise Exception('Client error')

    code = response.status_code
    # print(url)
    # print(inputcontent)
    # print(code)
    # print(response.text)

    if code != 200:
        if method != 'post' or code != 201:
            raise Exception('Http error '+str(code)+' '+response.text)

    if response.text == "":
        raise Exception('Http error '+str(code)+' Empty response')

    if method != 'post':
        return response.json()

    r = {}
    r['location'] = response.headers['Location']
    r['created'] = response.json()
    return r


def postTransfer(user_id, files, recipients, subject=None, message=None, expires=None, options=[]):
    if expires is None:
        expires = round(time.time()) + (default_transfer_days_valid*24*3600)

    print(expires)
    to = [x.strip() for x in recipients.split(',')]
    return call(
        'post',
        '/transfer',
        {},
        {
            'from': user_id,
            'files': files,
            'recipients': to,
            'subject': subject,
            'message': message,
            'expires': expires,
            'aup_checked': 1,
            'options': options
        },
        None,
        {}
    )


def putChunk(t, f, chunk, offset):
    return call(
        'put',
        '/file/'+str(f['id'])+'/chunk/'+str(offset),
        {'key': f['uid'], 'roundtriptoken': t['roundtriptoken']},
        None,
        chunk,
        {'Content-Type': 'application/octet-stream'}
    )


def fileComplete(t, f):
    return call(
        'put',
        '/file/'+str(f['id']),
        {'key': f['uid'], 'roundtriptoken': t['roundtriptoken']},
        {'complete': True},
        None,
        {}
    )


def transferComplete(transfer):
    return call(
        'put',
        '/transfer/'+str(transfer['id']),
        {'key': transfer['files'][0]['uid']},
        {'complete': True},
        None,
        {}
    )


def deleteTransfer(transfer):
    return call(
        'delete',
        '/transfer/'+str(transfer['id']),
        {'key': transfer['files'][0]['uid']},
        None,
        None,
        {}
    )

##########################################################################

def upload_file( fileobject, transferData, filesData, upload_chunk_size, debug):
    """This is the mp worker that replaces the last "try" block in the original script
    """
    fname = fileobject["name"]
    fsize = fileobject["size"]
    fstring = f"{fname}:{fsize}"
    fpath = filesData[fstring]["path"]

    try:
        # putChunks
        if debug:
            print('putChunks: '+fpath)
        with open(fpath, mode='rb', buffering=0) as fin:
            chunk_count = 0
            for offset in range(0, fsize, upload_chunk_size):
                if progress:
                    print('Uploading: '+fpath+' '+str(offset)+'-'+str(min(offset +
                        upload_chunk_size, fsize))+' '+str(round(offset/fsize*100))+'%')
                data = fin.read(upload_chunk_size)
                # print(data)
                putChunk(transferData, fileobject, data, offset)
                if debug:
                    chunk_count += 1
                    print(f"uploaded {chunk_count} chunks")
        # file complete
        if debug:
            print('fileComplete: '+fpath)
        fileComplete(transferData, fileobject)
        if progress:
            print('Uploading: '+fpath+' '+str(size)+' 100%')
    except Exception as e:
        raise(e)


def transfer_data_to_text(tdata):
    total_size = 0
    for f in tdata["files"]:
        total_size += f["size"]
    size_unit = "Bytes"
    if total_size > 1024**3:
        size_unit = "GB"
        total_size = total_size/(1024**3)
    elif total_size > 1024**2:
        size_unit = "MB"
        total_size = total_size/(1024**2)
    elif total_size > 1024:
        size_unit = "kB"
        total_size = total_size/(1024)
    if size_unit == "Bytes":
        size_str = f"{total_size} {size_unit}"
    else:
        size_str = f"{total_size:.2f} {size_unit}"

    url = tdata["recipients"][0]["download_url"]
    report_txt = f"""FileSender upload
transfer ID: {tdata["id"]}
uploaded by: {tdata["user_email"]}
total size:  {size_str}

recipient:   {tdata["recipients"][0]["email"]}
D/L link:    {url}

Files uploaded:
"""

    for fidx, f in enumerate(tdata["files"]):
        url = f"https://filesender.aarnet.edu.au/download.php?token={tdata['recipients'][0]['token']}&files_ids={f['id']}"
        ct_str = f"{fidx}".rjust( len(str(len(tdata["files"]))) )
        report_txt += f"""
{ct_str}: "{f["name"]}"
{" "*len(ct_str)}  {f["size"]:,} bytes 
{" "*len(ct_str)}  {url}
"""

    return report_txt

# -------------------------------------------------------
download_script_template = Template("""#!/usr/bin/bash

urls="${url_list}"
singleurl="${single_url}"

############################################################
# Help                                                     #
############################################################
Help()
{
   # Display Help
   echo "Add description of the script functions here."
   echo
   echo "Syntax: client_download_script.sh [-h|v|p|n|s]"
   echo "options:"
   echo "h     Print this Help."
   echo "v     Verbose mode."
   echo "s     Download all data as one single file (zip file by default, use '-a tar' to download as tar)"
   echo "a     Use with -s, specific archive format (zip|tar)"
   echo "p     Parallel download individual files (default n=8) using 'xargs'"
   echo "n     Number of concurrent downloads, default=8"
   echo "d     Dry-run. Show download commands without executing"
   echo
   echo "Example 1: Download individual files in parallel, with 6 concurrent downloads"
   echo "./client_download_script.sh -p -n 6"
   echo 
   echo "Example 2: Download all files combined into a single zip file"
   echo "./client_download_script.sh -s"
   echo 
   echo "Example 3: Download all files combined into a single tar file"
   echo "./client_download_script.sh -s -a tar"
   echo
}

############################################################
# Parallel_xargs                                           #
############################################################
Parallel_xargs()
{
    if [ $$dryrun = true  ]; then 
      echo 'echo $$urls | xargs -n 1 -P '"$${n_parallel}"' wget --content-disposition {}'
      exit
    elif [ $$verbose = true ] ; then
      echo 'echo $$urls | xargs -n 1 -P '"$${n_parallel}"' wget --content-disposition {}'
    else
      echo $$urls | xargs -n 1 -P $${n_parallel} wget --content-disposition {}
    fi
}

############################################################
# Single_download                                          #
############################################################
SingleArchiveDownload()
{
    if [ $$dryrun = true  ]; then 
      echo "wget --content-disposition \"$${singleurl}&archive_format=$${archive_format}\""
      exit
    elif [ $$verbose = true ]; then
      echo "wget --content-disposition \"$${singleurl}&archive_format=$${archive_format}\""
    else
      wget --content-disposition "$${singleurl}&archive_format=$${archive_format}"
    fi
}


OPTSTRING=":hsvpdn:a:"

mode="help"

n_parallel=8
verbose=false
archive_format=zip
dryrun=false

while getopts $${OPTSTRING} option; do
    case "$${option}" in
    h) # display help
       mode="help";;
    n) # test
       n_parallel=$${OPTARG};;
    v) # verbose
       verbose=true;;
    s) # single file
       mode="single";;
    p) # parallel download using xargs
       mode="parallel";;
    a) # archive_format
       archive_format=$${OPTARG};;
    d) # dry-run
       dryrun=true;;
    :)
      echo "Option -$${OPTARG} requires an argument."
      exit 1 ;;
   \?) # Invalid option
       echo "Error: Invalid option $${OPTARG}"
       exit;;
    esac
done


case $$mode in 
  parallel) # parallel download using xargs + wget
    Parallel_xargs
    exit;;
  single) # single file download
    SingleArchiveDownload
    exit;;
  help) # help
    Help
    exit;;
esac
""")
# -------------------------------------------------------




# -------------------------------------------------------------------------------

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# settings
base_url = 'https://filesender.aarnet.edu.au/rest.php'
default_transfer_days_valid = 21
username = None
apikey = None
homepath = expanduser("~")
recipients = None

config = configparser.ConfigParser()
config.read(homepath + '/.filesender/filesender.py.ini')
if 'system' in config:
    base_url = config['system'].get(
        'base_url', 'https://filesender.aarnet.edu.au/rest.php')
    default_transfer_days_valid = int(
        config['system'].get('default_transfer_days_valid', 10))
if 'user' in config:
    username = config['user'].get('username')
    apikey = config['user'].get('apikey')

if 'recipients' in config:
    recipients = config['recipients'].get('recipients')

# argv
parser = argparse.ArgumentParser()
parser.add_argument("files", help="path to file(s) to send", nargs='+')
parser.add_argument("-v", "--verbose", action="store_true")
parser.add_argument("-i", "--insecure", action="store_true")
parser.add_argument("-p", "--progress", action="store_true")
parser.add_argument("-s", "--subject", default="", type=str)
parser.add_argument("-m", "--message", default="", type=str)
parser.add_argument("-k", "--skip-email", action="store_true", default=False, help="Don't send email to recipient")
parser.add_argument("-n", "--n_procs", default=1, type=int, help="number of parallel uploads")

# if we have found these in the config file they become optional arguments
requiredNamed = parser.add_argument_group('required named arguments')
if username is None:
    requiredNamed.add_argument("-u", "--username", required=True)
else:
    parser.add_argument("-u", "--username")

if apikey is None:
    requiredNamed.add_argument("-a", "--apikey", required=True)
else:
    parser.add_argument("-a", "--apikey")
if recipients is None:
    requiredNamed.add_argument("-r", "--recipients", required=True)
else:
    parser.add_argument("-r", "--recipients")


# final reporting logs
parser.add_argument("--report", "-R", type=str, help="filepath for transfer report")
# reporttype = parser.add_mutually_exclusive_group(required=True)
parser.add_argument("--report-json", "-j", action="store_true", help="Output transfer report in JSON")
parser.add_argument("--report-text", "-t", action="store_true", help="Output transfer report in text (default)")
# parser.add_argument("--report-both", "-b", action="store_true", help="Report both JSON and txt formats")
parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode. No report.")

args = parser.parse_args()
debug = args.verbose
progress = args.progress
insecure = args.insecure
n_procs = args.n_procs
skip_email = args.skip_email

if args.username is not None:
    username = args.username

if args.apikey is not None:
    apikey = args.apikey

if args.recipients is not None:
    recipients = args.recipients


# -------------------------------------------------------------------------------


# -------------------------------------------------------------------------------
# test API, get info

# configs
try:
    response = requests.get(base_url+'/info', verify=True)
except requests.exceptions.SSLError as exc:
    if not insecure:
        print('Error: the SSL certificate of the server you are connecting to cannot be verified:')
        print(exc)
        print('For more information, please refer to https://www.digicert.com/ssl/. If you are absolutely certain of the identity of the server you are connecting to, you can use the --insecure flag to bypass this warning. Exiting...')
        sys.exit(1)
    elif insecure:
        print('Warning: Error: the SSL certificate of the server you are connecting to cannot be verified:')
        print(exc)
        print('Running with --insecure flag, ignoring warning...')
        response = requests.get(base_url+'/info', verify=False)
upload_chunk_size = response.json()['upload_chunk_size']

# -------------------------------------------------------------------------------
# test local file output

write_to_stdout = True
outprefix = None
outdir = None
if args.report:
    outprefix = os.path.abspath(args.report)
    outdir = os.path.dirname(outprefix)
    try:
        os.makedirs(outdir, exist_ok=True)
        fout = open(outprefix+".test", "w")
        fout.write("")
        fout.close()
        os.remove(outprefix + ".test")
        write_to_stdout = False
    except Exception as e:
        print("""
###########
# WARNING #
###########
Unable to write output to specified location. Printing to stdout instead
""")
        outprefix = None
        write_to_stdout = True

WRITE_JSON = args.report_json
WRITE_TEXT = args.report_text
QUIET = args.quiet

if not WRITE_JSON and not WRITE_TEXT:
    WRITE_TEXT = True

# -------------------------------------------------------------------------------

file_list_short_string = ",".join(args.files)
if len(args.files) > 6:
    file_list_short_string = ",".join( args.files[:3] ) + "..." + ",".join( args.files[-3:] )


if debug:
    print('base_url          : '+base_url)
    print('username          : '+username)
    print('apikey            : '+apikey)
    print('upload_chunk_size : '+str(upload_chunk_size)+' bytes')
    print('recipients        : '+recipients)
    print('files             : '+','.join(args.files))
    print('insecure          : '+str(insecure))


##########################################################################

# -------------------------------------------------------------------------------
# Start upload process

SPLIT_LIMIT = 1000

MAX_PER_SPLIT = int(0.95*SPLIT_LIMIT)

# postTransfer
if debug:
    print('postTransfer')

n_sets = 1
if len(args.files) < SPLIT_LIMIT:
    input_file_list = [args.files]
else:
    # split into sets of 0.95*SPLIT_LIMIT files
    input_file_list = []
    n_sets = int(len(args.files) / MAX_PER_SPLIT )
    if n_sets * 950 < len(args.files):
        n_sets += 1
    for n in range(n_sets):
        input_file_list.append(  args.files[n*MAX_PER_SPLIT:(n+1)*MAX_PER_SPLIT]  )
    


# ------------------------
# now iterate through sets of input_file_list

Responses = []

for file_set in range(n_sets):
    # get input file list
    files = {}
    filesTransfer = []
    for f in input_file_list[file_set]:
        fn_abs = os.path.abspath(f)
        fn = os.path.basename(fn_abs)
        size = os.path.getsize(fn_abs)
        files[fn+':'+str(size)] = {
            'name': fn,
            'size': size,
            'path': fn_abs
        }
        filesTransfer.append({'name': fn, 'size': size})

    troptions = {'get_a_link': skip_email}

    # sort by decreasing file size
    filesTransfer = sorted(filesTransfer, key=lambda x: x["size"], reverse=True)
    transfer = postTransfer(username,
                            filesTransfer,
                            recipients,
                            subject=args.subject,
                            message=args.message,
                            expires=None,
                            options=troptions)['created']

    # ----------------------------------------------------------------------
    # transferring data
    n_procs = min(n_procs, len(filesTransfer))
    task = partial(upload_file, 
                transferData=transfer, 
                filesData=files,
                upload_chunk_size=upload_chunk_size,
                debug=debug)
    pool = Pool(n_procs)
    pool.map(task, transfer['files'])
    pool.close()

    # transferComplete
    if debug:
        print('transferComplete')
    finalResponse = transferComplete(transfer)
    if progress:
        print('Upload Complete')
    Responses.append(finalResponse)

# --------------------------------------------------

if QUIET:
    exit()

# --------------------------------------------------
if WRITE_TEXT:
    if n_sets == 1:
        report_text = transfer_data_to_text(Responses[0])
    elif n_sets > 1:
        report_text = f"There were more than 1,000 files uploaded, so upload data were split into {n_sets} transfers\n"

        for n in range(n_sets):
            report_text += f"""
Set {n+1}:

{transfer_data_to_text(Responses[n])}

-------------------------------
"""
    if outprefix:
        fout = open(outprefix + ".txt", "w")
        fout.write(report_text)
        fout.close()
    else:
        print(f"""

#-----------------------------
# Text Report

{report_text}              

""")

if WRITE_JSON:
    if outprefix:
        fout = open( outprefix + ".json", "w" )
        fout.write( json.dumps(finalResponse) )
        fout.close()
    else:
        print(f"""

#-----------------------------
# JSON Report

{json.dumps(finalResponse, indent=1)}              


""")
    

# --------------------------------------------------
# WRITE DOWNLOAD SCRIPTS
for n in range(n_sets):
    if n_sets == 1:
        download_script = outprefix + ".client_download_script.sh"
    else:
        download_script = outprefix + f".client_download_script{n+1}.sh"
    
    res = Responses[n]
    url_list = []
    single_url = f"https://filesender.aarnet.edu.au/download.php?token={res['recipients'][0]['token']}&files_ids="
    for fidx, f in enumerate(res["files"]):
        url = f"https://filesender.aarnet.edu.au/download.php?token={res['recipients'][0]['token']}&files_ids={f['id']}"
        url_list.append(url)
        single_url += f"{f['id']}%2C"
    single_url = single_url[:-3]

    fout = open(download_script, "w")
    fout.write( download_script_template.substitute(single_url=single_url, url_list=("\n".join(url_list))) )
    fout.close()














