Installation

1. Download the repo
2. Create a virtual environment
    python -m venv venv
3. Activate the virtual environment
    venv\Scripts\activate
4. Install the requirements
    pip install -r requirements.txt 
5. Run Syntax:
* Download all icons from a set
    python iconify_dl.py <set_name> -o <output_dir>
* Download icons from a set that contain a certain keyword
    python iconify_dl.py <set_name> -o <output_dir> --contains <keyword>
* Download icons from a set that contain a certain keyword
    python iconify_dl.py <set_name> -o <output_dir> --include <keyword1>,<keyword2>
* Download icons from a set that contain a certain keyword
    python iconify_dl.py <set_name> -o <output_dir> --exclude <keyword1>,<keyword2>
* Download icons from a set that contain a certain keyword
    python iconify_dl.py <set_name> -o <output_dir> --debug

Examples:
* python iconify_dl.py https://icon-sets.iconify.design/fluent/ -o ./icons --debug 
* python iconify_dl.py fluent -o ./icons --debug 
* python iconify_dl.py mdi -o ./mdi --contains arrow --debug 
* python iconify_dl.py tabler -o ./tabler --include home,alarm --debug
