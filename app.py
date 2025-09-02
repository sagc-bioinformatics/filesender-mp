import streamlit as st
from download_script import MyHTMLParser, download_html, FileSenderDownload

st.title("Generate FileSender download commands")

url = st.text_input(label="AARNet FileSender URL:")



def parse_url(u):
    prefix = "https://filesender.aarnet.edu.au/?s=download"
    if u.startswith(prefix) == False:
        return False, "wrong prefix"
    token = ""
    bits = u[len(prefix)+1:].split("&")
    if len(bits) == 0:
        return False, ""
    for b_ in bits:
        if b_.startswith("token_"):
            token = b_.split("=")[1]

    return True, token



ParallelOption = "Multiple parallel downloads"
SingleFileOption = "Single archive file"
DEFAULT_PARALLEL_DOWNLOAD = 8

if url:
    parse_ok, message = parse_url(url)
    fsd = FileSenderDownload(url)
    if not parse_ok:
        st.write(f"Wrong URL format.")
        if message == "wrong prefix":
            st.write("""
URL should start with https://filesender.aarnet.edu.au/?s=download
""")
    else:
        token = message
        html_content = download_html(url)
        fs = FileSenderDownload(url)
        st.write("Parsing url:", url)
        st.write("Token: ", fs.token)
#        st.write("File IDs: ", " ".join(fs.fileids))

        st.markdown("<hr width=80%/>", unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            download_option = st.radio("Download method",
                options=(ParallelOption, SingleFileOption))

        with col2:
            if download_option==ParallelOption:
                parallel_n = st.number_input("Number of parallel downloads",min_value=1, value=8, step=1)
            elif download_option==SingleFileOption:
                archive_format = st.radio("Download archive format",
                options=("zip", "tar"))
        
        with col3:
            command_option = st.radio("Download command", options=("curl", "wget"))

        st.markdown("<hr width=80%/>", unsafe_allow_html=True)
        

        if download_option == SingleFileOption:
            fsd=FileSenderDownload(url, archive_format=archive_format)
            download_url=fsd.single_archive_link()
            st.write("Download command:")
            if command_option=="wget":
                st.code(f"wget --content-disposition \"{download_url}\"", language="bash")
            elif command_option =="curl":
                st.code(f"curl -L -C - -o filesender_transfer_{fs.token[0:8]}.{archive_format} \"{download_url}\"", language="bash")
        elif download_option == ParallelOption:
            filenames = "\n".join([ x[0] for x in fsd.name_links])
            urls = "\n".join([ x[1] for x in fsd.name_links])

            st.write("""
Better to copy and paste the content into a script and then execute the script.

But you _should_ be able to just copy and paste into a BASH terminal to run the command as well.

Please note, only the multiple parallel download with curl is capable of resuming a partial download, so this is the recommended method.
""")

            if command_option=="wget":
                st.code(f"""
#!/usr/bin/bash
                    
urls="{urls}"

paste <(printf "%s\\n" "${{filenames[@]}}") <(printf "%s\\n" "${{urls[@]}}") |\\
    xargs -n 2 -P {parallel_n} sh -c 'wget --content-disposition "$2"' _

""", language="bash")
            elif command_option=="curl":
                st.code(f"""
#!/usr/bin/bash
                    
urls="{urls}"
filenames="{filenames}"

paste <(printf "%s\\n" "${{filenames[@]}}") <(printf "%s\\n" "${{urls[@]}}") |\\
    xargs -n 2 -P {parallel_n} sh -c 'curl -L -C - -o "$1" "$2"' _

""", language="bash")