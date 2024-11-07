# filesender-mp
Adapting filesender for SAGC use, adding functionalities


`filesender_sagc.py` 
Modified from original filesender.py script, added:
* parallel upload
* logging
* some other stuff

`download_script.py`
Allow easy download via command line:
* supports parallel download or single archive file

`app.py`
Streamlit app, generates bash command for download (single archive or parallel using xargs)
