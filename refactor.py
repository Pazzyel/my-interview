import os

root_dir = r"d:\Coding\ResAgent\interview_python"

for subdir, dirs, files in os.walk(root_dir):
    for file in files:
        if file.endswith(".py") and file != "refactor.py":
            filepath = os.path.join(subdir, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Replace interview.guide. with nothing
            new_content = content.replace("interview.guide.", "")
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {filepath}")
