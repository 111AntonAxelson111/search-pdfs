import sys
import os
import tkinter as tk
from tkinter import filedialog
import fitz  # PyMuPDF
from datetime import datetime
from typing import List
from pathlib import Path
import json
import time
from icecream import ic
from rich.console import Console
#from rich.table import Table
from rich.panel import Panel
#from rich.box import SIMPLE
from rich.text import Text
from rich.style import Style

ic.disable()
console = Console()
start_time = time.time()

def rich_print_pdf_result(pdfpath, tot_words, sstrings_findings, txt_append, skip0=True):
    filename = os.path.basename(pdfpath)
    width = console.size.width // 2

    lines: List[Text] = []
    lines.append(Text(f"pdf: {filename}\n"))
    lines.append(Text(f"total words: {tot_words}\n\n"))

    for sstring, data in sstrings_findings.items():
        count = int(data["count"])
        pages_found = data["pages where found"].strip()
        ratio = f"{count/tot_words:.6f} ({count}/{tot_words})"

        style_count_green = Style(color="green", bold=True)
        style_count_red   = Style(color="red", bold=True)
        style_string      = Style(color="white")
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
    console.print(sep)
    console.print(block)
    console.print(sep)

    txt_append("\n")



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




def main():

    if (sys.argv[1]).lower().strip()=="help":
        display_help()


    def txt_append(text):
        with open(txt_path, "a", encoding="utf-8") as txt:
            txt.write(text)


    root = tk.Tk()
    root.withdraw()

    target_folder = Path(filedialog.askdirectory(title="Select folder containing PDFs"))
    if not target_folder:
        print("No folder selected")
        ic(target_folder)
        sys.exit()
    ic(target_folder)

    save_folder = target_folder / "search"
    if not os.path.exists(save_folder):
        save_folder.mkdir()
    ic(save_folder)

    txt_path = os.path.join(save_folder, "!!!!word_counts.txt")
    ic(txt_path)

    all_pdf_paths = [] #we collect all .pdf file in directory we target
    for file in os.listdir(target_folder):
        if file.lower().endswith(".pdf"):
            fullpath = os.path.abspath(os.path.join(target_folder, file))
            all_pdf_paths.append(fullpath)

    
    sstrings = [w for w in sys.argv[1:] if w]  #we parse search strings from user

    if not sstrings:
        display_help()
        print("you need to give strings that it should search for.")
        sys.exit()

    


    #here we have:
    #all_pdf_paths  #pdf paths we will be searching
    #sstrings    #these are strings we will be counting how many times they are in pdf document. sstring==search string
    #txt_path  #this is file that is in target folder that we will write results to
    #save_folder #this is folder we save result and we cache json files

    #now we do main thing
    txt_append("\n\n\n\n\n\n\n===============================================================\n"+f"{sstrings}\n"+f"{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}\n\n")#start
    print("====\n====\n====\n\nTarget folder:"+f"\033[95m{os.path.abspath(target_folder)}\033[0m "+"\n") #yellow 93

    for pdfpath in all_pdf_paths:

        pdfpath_name = Path(pdfpath).stem 
        ic(pdfpath_name)
        json_file_path = save_folder / f"{pdfpath_name}.json"
        ic(json_file_path)
        ic(os.path.exists(json_file_path))


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

        sstrings_findings={ 
            sstring:{"count":0,"pages where found":""} 
            for sstring in sstrings
            }

        for page_number, page_text in pages.items():

            for sstring in sstrings:
                if sstring in page_text:
                    sstrings_findings[sstring]["count"]+=1
                    sstrings_findings[sstring]["pages where found"]+=f" {page_number} "

        rich_bool_flag=True
        if rich_bool_flag:
            rich_print_pdf_result(pdfpath, tot_words, sstrings_findings, txt_append)
        for sstring, data in sstrings_findings.items():
            count = int(data["count"])
            pages_found = data["pages where found"].strip()
        
            len_count = len(str(count))

            if rich_bool_flag==False:
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


        ic(sstrings_findings)
    print("\nFile created:"+f"\033[95m{txt_path}\033[0m"+f"\nelapsed time:{time.time()-start_time}\n====\n====\n====\n")
    txt_append(f"\n\nelapsed time:{time.time()-start_time}\n===============================================================\n\n\n")



if __name__=="__main__":
    main()