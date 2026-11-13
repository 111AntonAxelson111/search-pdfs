import sys
import os
import subprocess
import shutil
import ctypes
import tkinter as tk
from tkinter import filedialog
import pymupdf as fitz  # PyMuPDF
from datetime import datetime
from typing import List,Dict
from pathlib import Path
import json
import time
import re 



from icecream import ic
from rich.console import Console
#from rich.table import Table
from rich.panel import Panel
#from rich.box import SIMPLE
from rich.text import Text
from rich.style import Style

from dataclasses import dataclass




@dataclass
class UserInputCmd():
    open_file =   ("view","open","viewpdf","openpdf")
    open_folder = ("view","open","viewpdf","openpdf")
    new_dir  = ("--new-folder","--new-dir")
    help = ("help")
    exit = ("exit")

parse = UserInputCmd()





ic.enable()
console = Console()
start_time = time.time()


#======================================================
def rich_print_pdf_result(pdfpath, tot_words, sstrings_findings, txt_append,id_of_path, skip0=True,skip_if_all0=True):
    
    if tot_words==0:tot_words=1#division by zero error #TODO bättre lösning inte scattra denna typ av rad överallt
    filename = os.path.basename(pdfpath)
    width = console.size.width // 2

    lines: List[Text] = [] 
    
    
    lines.append(Text(f"pdf: {filename}\n"))
    lines.append(Text(f"id to view path: {id_of_path}\n"))
    lines.append(Text(f"total words: {tot_words}\n\n"))

    all0_bool=True
    for sstring, data in sstrings_findings.items():

        count = int(data["count"])
        pages_found = data["pages where found"].strip()
        ratio = f"{count/tot_words:.6f} ({count}/{tot_words})"

        style_count_green = Style(color="green", bold=True)
        style_count_red   = Style(color="red", bold=True)
        style_string      = Style(color="white")
        
        if count>0:
            all0_bool=False
        
        if ((skip0==True)and(count!=0)):
            line1 = Text()
            if count == 0:
                line1.append(f"{count:>4} ", style=style_count_red)
                line1.append(f" {sstring}\n", style=style_string)
                lines.append(line1)
            else:
                line1.append(f"{count:>4} ", style=style_count_green)
                line1.append(f" {sstring}\n", style=style_string)
                lines.append(line1)
                

            lines.append(Text(ratio + "\n", style="cyan"))
            if pages_found:
                lines.append(Text(f"pages: {pages_found}\n", style="cyan"))
            lines.append(Text("\n"))

            txt_append(f"{count} '{sstring}'\n")
            txt_append(f"{ratio}\n")
        if pages_found:
            txt_append(f"pages: {pages_found}\n")
        txt_append("\n")

    block = Text.assemble(*lines)

    # NEW: dynamic separators instead of a rigid panel
    sep = Text("-" * width, style="white")
    
    if skip_if_all0==False: 
        console.print(sep)
        console.print(block)
        console.print(sep)
    
    if skip_if_all0==True and all0_bool==False:
        console.print(sep)
        console.print(block)
        console.print(sep)

    txt_append("\n")

def aarich_print_pdf_result(pdfpath, tot_words, sstrings_findings, txt_append,skip0=True):
    filename = os.path.basename(pdfpath)
    width = console.size.width // 2

    # Build styled Text block (counts in bold gold)
    lines: List[Text] = []
    lines.append(Text(f"pdf: {filename}\n"))
    lines.append(Text(f"total words: {tot_words}\n\n"))

    for sstring, data in sstrings_findings.items():
        count = int(data["count"])
        pages_found = data["pages where found"].strip()
        ratio = f"{count/tot_words:.6f} ({count}/{tot_words})"

        # create a Text line where count is bold gold and the rest is normal
        line1 = Text()
        if count==0:
            if not skip0:
                line1.append(f"{count:>4} ", style="bold red")
        else:
            line1.append(f"{count:>4} ", style="bold green")

        line1.append(f" {sstring}\n")
        lines.append(line1)

        # ratio line (dim to de-emphasize)
        line2 = Text(ratio + "\n", style="cyan")#style="dim"
        lines.append(line2)

        if pages_found:
            line3 = Text(f"pages: {pages_found}\n", style="cyan")
            lines.append(line3)

        lines.append(Text("\n"))

        # write plain text to file (no markup)
        txt_append(f"{count} '{sstring}'\n")
        txt_append(f"{ratio}\n")
        if pages_found:
            txt_append(f"pages: {pages_found}\n")
        txt_append("\n")

    # join Text lines into one block
    block = Text.assemble(*lines)

    # Print minimal panel with the styled block
    console.print(
        Panel(
            block,
            width=width,
            border_style="white",
            padding=(1, 2)
        )
    )

    txt_append("\n")
#======================================================






def read_json(path):
    with open(path, 'r',encoding="utf-8") as f:
        dict = json.load(f)
    return dict

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def display_help():
    help_text = """
pdf-search.py — search strings inside PDFs and cache page text

Purpose
  Search every PDF in a selected folder for one or more search strings,
  count occurrences per page, and write human-readable results to:
    <selected_folder>/search/!!!!word_counts.txt
  Per-PDF caches are stored as JSON in:
    <selected_folder>/search/<pdf_stem>.json

Usage
  python pdf-search.py <string1> [string2 ... stringN]
  - Start the script, choose the folder containing PDFs in the dialog,
    then the script will process all .pdf files in that folder.

Behavior notes
  - Page text is lowercased before searching, so searches are case insensitive.
  - The script caches page text and total word counts in JSON files to speed up repeated runs.
  - Results are appended to the text file '!!!!word_counts.txt' inside the search folder.
  - If you pass the single argument 'help' the script shows this message.

Examples
  1) Search for a single word:
     python pdf-search.py invoice

     Expected result:
       - A folder <selected_folder>/search is created if missing.
       - For each PDF, a JSON cache and a formatted panel printed to the terminal.
       - Summary lines appended to <selected_folder>/search/!!!!word_counts.txt

  2) Search for multiple strings:
     python pdf-search.py "data breach" password "social security"

     Expected result:
       - Counts and pages where each string appears are shown and saved.

  3) Show help:
     python pdf-search.py help

Exit
  The function prints this message and returns; the main flow will exit after showing help.
"""
    print(help_text.strip())

def parse_sstrings(first_time:bool,raw_user_inp)->List[str]:
    
    item_check_if_error_happens_here = "ööööööö  item_check_if_error_happens_here 99999"
    lis_sstring = [item_check_if_error_happens_here]

    #these do this:    " string a "   "stringb" "string c"   -> [" string a ","stringb","string c"]
    if first_time:
        lis_sstring:List[str] = [w for w in sys.argv[1:] if w]  #we parse search strings from user
    else:
        #######parse search strings from user input###########
        lis_sstring:List[str] = []
        cur_s=""
        ssss=""
        ööö=0
        read_bool=False
        for s in raw_user_inp:
            if s=='"' and ööö==0:
                read_bool=True
                ööö=1
                lis_sstring.append(cur_s)
                continue
            if s=='"' and ööö==1:
                read_bool=False
                ööö=1
                cur_s=""
                continue
            
            if read_bool:
                cur_s+=s
        #######parse search strings from user input###########
        #
        #### we had this before    
        #sstrings:List[str] = re.findall(r'"([^"]*)"|(\S+)', raw_user_inp)
        ##ic(sstrings)
        ######
    
    
    
    
    
    #==========================================
    if (lis_sstring == [item_check_if_error_happens_here]) or (lis_sstring == []):
        
        print("1 lis_sstring: ",lis_sstring)
        display_help()#TODO maybe we have one diplay help with many input and many cases
        print("you need to give strings that it should search for.")
        raise
        #sys.exit()
    
    if not isinstance(lis_sstring,list):
        print("2 lis_sstring:",lis_sstring)
        raise
    
    # all inner item is string and longer than one
    for sstring in lis_sstring:
        if not(isinstance(sstring,str)):
            print("3 lis_sstring:",lis_sstring)
            raise
        if not(len(sstring)>1):
            print("4 lis_sstring:",lis_sstring)
            raise
    #==========================================
    
    
    return lis_sstring



















#===================================================================
def open_with_sumatrapdf(file_path, sumatra_path=None):
    """
    Opens a PDF file with SumatraPDF – includes user's specific path
    """
    file_path = Path(file_path)

    if not file_path.exists():
        print(f"Error: File not found - {file_path}")
        return False

    if file_path.suffix.lower() != '.pdf':
        print(f"Error: Not a PDF file - {file_path}")
        return False

    # If no path provided, search common locations
    if sumatra_path is None:
        # Build list of possible SumatraPDF locations
        possible_paths = [
            
            # Standard Program Files locations
            Path("C:/Program Files/SumatraPDF/SumatraPDF.exe"),
            Path("C:/Program Files (x86)/SumatraPDF/SumatraPDF.exe"),
            # Local AppData (generic)
            Path.home() / "AppData/Local/SumatraPDF/SumatraPDF.exe",
            # From PATH environment
            Path(shutil.which("SumatraPDF")) if shutil.which("SumatraPDF") else None,
            # Portable in current directory
            Path.cwd() / "SumatraPDF.exe",
        ]

        # Filter out None and check existence + is_file
        for path in possible_paths:
            if path and path.exists() and path.is_file():
                sumatra_path = path
                break

        if sumatra_path is None:
            print("Error: Could not find SumatraPDF installation.")
            print("Please provide the path manually or install SumatraPDF.")
            return False

    # Now open the file
    try:
        if sys.platform == "win32":
            subprocess.run([str(sumatra_path), str(file_path)], check=True)
        else:
            subprocess.run(["xdg-open", str(file_path)], check=True)

        print(f"Opened: {file_path}")
        return True

    except Exception as e:
        print(f"Error opening file: {e}")
        return False

def bbbbbopen_with_sumatrapdf(file_path, sumatra_path=None)->None | bool:
    
    #"C:\Users\anton\AppData\Local\SumatraPDF\SumatraPDF.exe"
    
    
    # ... (existing code up to finding sumatra_path)
    if sumatra_path is None:
        ic("sumatra_path is None, attempting to locate automatically")
        possible_paths = [
            Path("C:/Program Files/SumatraPDF/SumatraPDF.exe"),
            Path("C:/Program Files (x86)/SumatraPDF/SumatraPDF.exe"),
        ]
        
        # Add from PATH if found
        which_result = shutil.which("SumatraPDF")
        if which_result:
            possible_paths.append(Path(which_result))
        
        # Also check current directory for portable version
        cwd_exe = Path.cwd() / "SumatraPDF.exe"
        possible_paths.append(cwd_exe)
        
        ic(f"Possible paths: {possible_paths}")

        for path in possible_paths:
            ic(f"Checking: {path} exists? {path.exists()} and is_file? {path.is_file()}")
            if path.exists() and path.is_file():
                sumatra_path = path
                ic(f"Found SumatraPDF at: {sumatra_path}")
                break

        if sumatra_path is None:
            print("Error: Could not find SumatraPDF installation")
            print("Please provide the path manually or install SumatraPDF")
            ic("Returning False because SumatraPDF not found")
            return False
    else:
        ic(f"Using provided sumatra_path: {sumatra_path}")
        # Even if provided, verify it's a file
        if not sumatra_path.is_file():
            print(f"Error: Provided SumatraPDF path is not a file: {sumatra_path}")
            return False

def open_with_sumatrapdfaaa(file_path, sumatra_path=None)->None | bool:
    """
    Opens a PDF file with SumatraPDF – DEBUG VERSION with extensive ic output
    """
    ic.enable()  # temporarily enable for this function

    ic("=" * 50)
    ic("ENTER open_with_sumatrapdf")
    ic(f"file_path argument: {file_path} (type: {type(file_path)})")
    ic(f"sumatra_path argument: {sumatra_path}")
    # Convert to Path object
    try:
        file_path = Path(file_path)
        ic(f"file_path converted: {file_path}")
    except Exception as e:
        ic(f"Path conversion failed: {e}")
        print(f"Unexpected error: {e}")
        return False

    # Check if file exists
    ic(f"file_path.exists(): {file_path.exists()}")
    if not file_path.exists():
        print(f"Error: File not found - {file_path}")
        ic("Returning False because file does not exist")
        return False

    # Check if it's a PDF
    ic(f"file_path.suffix: {file_path.suffix}")
    if file_path.suffix.lower() != '.pdf':
        print(f"Error: Not a PDF file - {file_path}")
        ic("Returning False because not a PDF")
        return False

    # Find SumatraPDF executable
    if sumatra_path is None:
        ic("sumatra_path is None, attempting to locate automatically")
        # Common installation locations
        possible_paths = [
            Path("C:/Program Files/SumatraPDF/SumatraPDF.exe"),
            Path("C:/Program Files (x86)/SumatraPDF/SumatraPDF.exe"),
            Path(shutil.which("SumatraPDF") or ""),
            Path.cwd() / "SumatraPDF.exe",
        ]
        ic(f"Possible paths: {possible_paths}")

        for path in possible_paths:
            ic(f"Checking: {path} exists? {path.exists()}")
            if path.exists():
                sumatra_path = path
                ic(f"Found SumatraPDF at: {sumatra_path}")
                break

        if sumatra_path is None:
            print("Error: Could not find SumatraPDF installation")
            print("Please provide the path manually or install SumatraPDF")
            ic("Returning False because SumatraPDF not found")
            return False
    else:
        ic(f"Using provided sumatra_path: {sumatra_path}")

    # Verify that sumatra_path is a file (not a directory)
    ic(f"sumatra_path.is_file(): {sumatra_path.is_file()}")
    if not sumatra_path.is_file():
        print(f"Error: SumatraPDF path is not a file: {sumatra_path}")
        ic("Returning False because sumatra_path is not a file")
        return False

    try:
        # Open the PDF with SumatraPDF
        if sys.platform == "win32":
            ic("Platform is Windows")
            if sumatra_path:
                cmd = [str(sumatra_path), str(file_path)]
                ic(f"Running command: {cmd}")
                result = subprocess.run(cmd, check=True)
                ic(f"subprocess.run returned: {result}")
            else:
                ic("Using os.startfile as fallback")
                os.startfile(str(file_path))
        else:
            ic("Platform is not Windows, using xdg-open")
            subprocess.run(["xdg-open", str(file_path)], check=True)

        print(f"Successfully opened: {file_path}")
        ic("Returning True")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error opening file: {e}")
        ic(f"subprocess.CalledProcessError: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        ic(f"Unexpected exception: {e}", exc_info=True)
        return False
    finally:
        ic("EXIT open_with_sumatrapdf")
        ic("=" * 50)
        ic.disable()
#===================================================================

def get_all_pdf_paths(target_folder):
    all_pdf_paths = [] #we collect all .pdf file in directory we target
    for file in os.listdir(target_folder):
        if file.lower().endswith(".pdf"):
            fullpath = os.path.abspath(os.path.join(target_folder, file))
            all_pdf_paths.append(fullpath)
    
    if all_pdf_paths==[]:
        print("all_pdf_paths:  ",all_pdf_paths)
        raise
    
    return all_pdf_paths

def gui_get__pdf_dir()->Path:
    """get with windows
    ############# get with windows gui  
    ############ it was not so nice    
    ####    try:
    ####        # 1. Check OS is Windows
    ####        # 2. Check PowerShell exists in PATH
    ####        # 3. Check a GUI session is active (GetSystemMetrics(0) > 0 verifies a screen/desktop exists)
    ####        condition = (
    ####            os.name == "nt"
    ####            and shutil.which("powershell") is not None
    ####            and ctypes.windll.user32.GetSystemMetrics(0) > 0
    ####        )
    ####    except Exception:
    ####        condition = False
    ####
    ####    if condition:
    ####        ps_script = '''
    ####        Add-Type -AssemblyName System.Windows.Forms
    ####        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    ####        $dialog.Description = 'Select folder containing PDFs'
    ####        $dialog.UseDescriptionForTitle = $true
    ####        if ($dialog.ShowDialog() -eq 'OK') {
    ####            Write-Output $dialog.SelectedPath
    ####        }
    ####        '''
    ####
    ####        result = subprocess.run(
    ####            ["powershell", "-NoProfile", "-Command", ps_script],
    ####            capture_output=True,
    ####            text=True,
    ####        )
    ####
    ####        selected_path = result.stdout.strip()
    ####
    ####        if not selected_path:
    ####            print("No folder selected")
    ####            ic(selected_path)
    ####            raise
    ####
    ####        target_folder = Path(selected_path)
    ####        ic(target_folder)
    ####        return target_folder
    ####    
    ####    else:
    """
    root = tk.Tk()
    root.withdraw()

    target_folder = Path(filedialog.askdirectory(title="Select folder containing PDFs"))
    
    if not target_folder:
        print("No folder selected")
        ic(target_folder)
        raise
    ic(target_folder)
    return target_folder

# Optional: Function to find SumatraPDF automatically
def find_sumatrapdf()->Path | None:
    """
    Searches for SumatraPDF installation and returns the path if found
    """
    common_paths = [
        Path("C:/Program Files/SumatraPDF/SumatraPDF.exe"),
        Path("C:/Program Files (x86)/SumatraPDF/SumatraPDF.exe"),
        Path("C:/Users") / Path.home().name / "AppData/Local/SumatraPDF/SumatraPDF.exe",
        Path("C:/PortableApps/SumatraPDF/SumatraPDF.exe"),
        Path.cwd() / "SumatraPDF.exe",
        Path.cwd() / "SumatraPDF-portable.exe",
    ]
    
    for path in common_paths:
        if path.exists():
            return path
    
    # Try searching in PATH
    which_path = shutil.which("SumatraPDF")
    if which_path:
        return Path(which_path)
    
    return None

def open_file_finder_with_directory_path(start_path)->Path | None:
    """
    Opens a file selection dialog starting from the specified path
    
    Args:
        start_path: The directory path to start the dialog in
    
    Returns:
        Path object of selected file, or None if cancelled
    """
    root = tk.Tk()
    root.withdraw()
    
    start_path = Path(start_path)
    
    if not start_path.exists():
        print(f"Warning: Path {start_path} doesn't exist, using current directory")
        start_path = Path.cwd()
    
    # For file selection
    selected_file = filedialog.askopenfilename(
        title="Select a PDF file",
        initialdir=start_path,
        filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
    )
    
    root.destroy()
    
    # Return Path object if file selected, otherwise None
    return Path(selected_file) if selected_file else None





def main():
    def txt_append(text):
        with open(txt_path, "a", encoding="utf-8") as txt:
            txt.write(text)
            
    first_time=True
    target_folder= gui_get__pdf_dir()
    
    id_counter=0
    path_id_lis_last_results=[] #used to save old results
    while True:
        
        if not first_time:
            raw_user_inp = input(">")
        else:
            raw_user_inp="first time"   
        
        #this if user wants help       
        if (first_time):
            if (sys.argv[1]).lower().strip()=="help":   
                display_help()
                continue
        else:
            if ( (raw_user_inp).lower().strip()=="help"  ):
                display_help()
                continue

        #this if user wants exit
        if (first_time):
            if (sys.argv[1]).lower().strip()=="exit":   
                sys.exit()
        else:
            if ( (raw_user_inp).lower().strip()=="exit"  ):
                sys.exit()
                
        
        
        
        
        
        
        
        
        
        
        
        # What happens here is that we eiter open specific document or the target pdf directory
        # We do this by 
        #
        #this if user wants to view pdf
        #TODO we have this being to complex we could simplify this
        #TODO also "open" is written two times     

        
        try:
            bool_user_open_file =  (
                (
                    not first_time
                ) 
                and 
                ( 
                    raw_user_inp.lower().strip().split()[0]
                    in [s for s in parse.open_file]
                )
                and
                (
                    len(raw_user_inp.lower().strip().split())==2
                )
                and
                (   
                    (  raw_user_inp.lower().strip().split()[1]  ).isnumeric()
                )
            )
        except:
            ic("öööö")
            bool_user_open_file=False
        
        bool_user_open_pdf_dir =  (
            (
                not first_time
            ) 
            and 
            (
                len(raw_user_inp.lower().strip().split())==1
            ) 
            and 
            ( 
                raw_user_inp.lower().strip().split()[0] 
                in [s for s in parse.open_folder]
            )
        )
        
        
        
        """
        first_time 
        or ( (raw_user_inp).lower().strip() =="--new-folder" ) 
        or ( (raw_user_inp).lower().strip() == "--new-dir" )
        """
        bool_user_change_pdf_dir = (
            (
                (raw_user_inp).lower().strip()
                in parse.new_dir
            )
        )
        
        
        
        
        """
        We search the pdf files for sstrings
        if:{
        * no other commands are in it 
        AND
        * the number of (") is even
        }
        """
        n__double_quotation_mark=0 
        for char in raw_user_inp:
            if char=='"':
                n__double_quotation_mark+=1
        if (n__double_quotation_mark%2)==0:
            is_even = True
        else:
            is_even = False
        
        cmd_strings = [
            list(parse.open_file[:])
            +list(parse.open_folder[:])
            +list(parse.new_dir[:])
            +list(parse.help[:])
            +list(parse.exit[:])
        ]
        no_user_cmd_strings= any(
            (user_string not in cmd_strings) 
            for user_string in (raw_user_inp).lower().strip().split()
            )
        
        bool_user_search_sstrings_in_pdf_dir = (

            (
                no_user_cmd_strings
            )
            and
            (              
                is_even == True # t.ex ' "hej" "hej" "hej" ' ---n quotation marks--> 6 ---is_even--> True
            )
        )
        
        
        

            
        if bool_user_open_file:
            #assert len(raw_user_inp)==1 
            # here user write: "--view <number>" or "--open <number>" or "--viewpdf <number>" or "--openpdf <number>" 
            # example: --open 2
            # example: --view 99
            # example: --viewpdf 99
            # example: --openpdf 22
            
            id_of_path = int((raw_user_inp).lower().strip().split()[1])

            pdf_path_that_should_be_opened=None
            for path_saved,id_saved in path_id_lis_last_results:
                if id_of_path==id_saved:
                    pdf_path_that_should_be_opened=path_saved
                
            #ic("a1")
            open_with_sumatrapdf(pdf_path_that_should_be_opened)
            #ic("a2")

        elif bool_user_open_pdf_dir:
            #
            #  here user write "--view" or "--open" or "--viewpdf" or "--openpdf"
            #
            assert len(raw_user_inp)==1            
            pdf_path_that_should_be_opened=open_finder_with_directory_path(target_folder)
            open_with_sumatrapdf(pdf_path_that_should_be_opened)
            continue
        
        #
        # we get target folder,  
        # target folder is folder that we will search all pdfs in 
        # 
        elif bool_user_change_pdf_dir:
            target_folder = gui_get__pdf_dir()
            continue

        elif bool_user_search_sstrings_in_pdf_dir:


            #these do this:    " string a "   "stringb" "string c"   -> [" string a ","stringb","string c"]
            first_time:bool ; raw_user_inp:str
            lis_sstring:List[str] = parse_sstrings(first_time,raw_user_inp)
            
            
            #TODO rename to cache
            save_folder = target_folder / "search"
            if not os.path.exists(save_folder):
                save_folder.mkdir()
            
            txt_path = os.path.join(save_folder, "!!!!word_counts.txt")
            ic(txt_path)
            
            
            all_pdf_paths = get_all_pdf_paths(target_folder)


            #
            #here we have:
            #all_pdf_paths  #pdf paths we will be searching
            #sstrings    #these are strings we will be counting how many times they are in pdf document. sstring==search string
            #txt_path  #this is file that is in target folder that we will write results to
            #save_folder #this is folder we save result and we cache json files
            #
            #now we do main thing
            txt_append("\n\n\n\n\n\n\n===============================================================\n"+f"{lis_sstring}\n"+f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}\n\n")#start
            print("====\n====\n====\n\nTarget folder:"+f"\033[95m{os.path.abspath(target_folder)}\033[0m "+"\n") #yellow 93

            for pdfpath in all_pdf_paths:
                
                id_counter+=1
                path_id_lis_last_results.append([pdfpath,id_counter])
                pdfpath_name = Path(pdfpath).stem 
                ###ic(pdfpath_name)
                json_file_path = save_folder / f"{pdfpath_name}.json"
                ###ic(json_file_path)
                ###ic(os.path.exists(json_file_path))


                new_json={"tot_words":"","pages":""}
                tot_words=0
                pages={}
                if os.path.exists(json_file_path):
                    json_content = read_json(json_file_path)
                    pages=json_content["pages"]
                    tot_words=json_content["tot_words"]
                else:
                    ###### here we get values and we write to the file
                    try:
                        doc = fitz.open(pdfpath)
                        for doc_page in doc:
                            try:
                                text= str(doc_page.get_text().lower())
                                tot_words+= len(text.split())
                                doc_page_number = int(doc_page.number)
                                pages[doc_page_number] = text

                            except Exception as e:
                                print("Inner","e",e)
                    except Exception as e:
                        print("outer","e",e)

                    new_json["pages"]=pages
                    new_json["tot_words"]=tot_words
                    write_json(json_file_path,new_json)
                        

                # Here we now have 
                # tot_words 
                # pages
                # 
                # now we do so that we iterate over page 
                #txt_append(f"pdf: {os.path.basename(pdfpath)}"+"\n(\n"+f"words in pdf:{tot_words}\n")
                #print(f"\033[93mpdf: {os.path.basename(pdfpath)}\033[0m"+"\n(\n"+f"total words in pdf:{tot_words}\n")
                #
                #sstrings_findings this is where we write search
                #
                #
                #ic("1ääääääää",lis_sstring)
                lis_sstring__findings:Dict[Dict[str,int|str]]={ 
                    sstring:{"count":0,"pages where found":""} 
                    for sstring in lis_sstring
                    }
                #ic("2ääääääää",lis_sstring__findings)

                for page_number, page_text in pages.items():

                    for sstring in lis_sstring:
                        #ic("3ääääääää",sstring)
                        #ic("4ääääääää",lis_sstring)
                        #raise
                        if sstring in page_text:
                            lis_sstring__findings[sstring]["count"]+=1
                            lis_sstring__findings[sstring]["pages where found"]+=f" {page_number} "
                
                #################ic(sstrings_findings)
                
                rich_bool_flag=True
                #################if rich_bool_flag:
                #################    rich_print_pdf_result(pdfpath, tot_words, sstrings_findings, txt_append,id_counter)
                
                assert all( 
                        (item[0] in lis_sstring)      
                        for item in lis_sstring__findings.items()
                        )
                
                
                #
                #  Here we display the results
                #
                #
                for sstring, data in lis_sstring__findings.items():
                    
                    
                    
                    count = int(data["count"])
                    pages_found = data["pages where found"].strip()
                
                    len_count = len(str(count))
                    if tot_words==0:tot_words=1#division by zero error #TODO bättre lösning inte scattra denna typ av rad överallt
                    if count==0:continue
                    
                    
                    if rich_bool_flag==True:#True:#False
                        # terminal
                        s = ""
                        s += "\033[30;47m"#ny
                        s += (str(count) + " " * 100)[:len_count + (2 if len_count % 2 == 0 else 1)]
                        s += "\033[0m"
                        s += f"'{sstring}'"
                        print(s)
                    
                        s = ""
                        s += "\033[96m"
                        s += (str(count / tot_words) + " " * 100)[:len_count + (2 if len_count % 2 == 0 else 1)]
                        s += "\033[0m"
                        s += f"{count}/{tot_words}"
                        print(s)
                    
                        if pages_found:
                            print(f"pages: {pages_found}")
                        print()
                
                    # to textfile
                    s = ""
                    s += (str(count) + " " * 100)[:len_count + (1 if len_count % 2 == 0 else 0)]
                    s += f"'{sstring}'\n"
                    txt_append(s)
                
                    s = ""
                    s += (str(count / tot_words) + " " * 100)[:len_count + (1 if len_count % 2 == 0 else 0)]
                    s += f"{count}/{tot_words}\n"
                    txt_append(s)
                
                    if pages_found:
                        txt_append(f"pages: {pages_found}\n")
                
                if rich_bool_flag==False:
                    print(")")
                    print()
                txt_append("\n")
                txt_append(")\n")
                txt_append("\n")


                #ic(sstrings_findings)
            print("\nFile created:"+f"\033[95m{txt_path}\033[0m"+f"\nelapsed time:{time.time()-start_time}\n====\n====\n====\n")
            txt_append(f"\n\nelapsed time:{time.time()-start_time}\n===============================================================\n\n\n")
            first_time=False


if __name__=="__main__":
    main()


