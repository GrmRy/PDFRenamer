import zipfile

def save_zip(file_paths, save_path):
    with zipfile.ZipFile(save_path, 'w') as z:
        for file in file_paths:
            z.write(file, arcname=file.name)
