import json
import os
from pathlib import Path
import logging
import shutil
from datetime import datetime

TEMPLATE_FILENAME = "pdf_renamer_templates.json"
BACKUP_DIR = "backups"
MAX_BACKUP_FILES = 10

class TemplateError(Exception):
    """Custom exception for template-related errors."""
    pass

class ConfigError(Exception):
    """Custom exception for configuration-related errors."""
    pass

def get_app_data_dir():
    """
    Get the appropriate directory for storing application data.
    Creates the directory if it doesn't exist.
    
    Returns:
        Path: Path to application data directory
    """
    try:
        # Use user's home directory for cross-platform compatibility
        app_dir = Path.home() / ".pdf_renamer"
        app_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        (app_dir / BACKUP_DIR).mkdir(exist_ok=True)
        
        return app_dir
    except Exception as e:
        # Fallback to current directory if can't create in home
        logging.warning(f"Cannot create app directory in home, using current directory: {e}")
        current_dir = Path.cwd() / ".pdf_renamer_data"
        current_dir.mkdir(exist_ok=True)
        (current_dir / BACKUP_DIR).mkdir(exist_ok=True)
        return current_dir

def get_template_file_path():
    """Get the full path to the template file."""
    return get_app_data_dir() / TEMPLATE_FILENAME

def validate_template_structure(template):
    """
    Validates the structure of a template dictionary.
    
    Args:
        template (dict): Template to validate
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not isinstance(template, dict):
        return False, "Template harus berupa dictionary"
    
    # Check required keys
    if "aturan" not in template:
        return False, "Template harus memiliki key 'aturan'"
    
    # Validate rules
    rules = template["aturan"]
    if not isinstance(rules, list):
        return False, "Field 'aturan' harus berupa list"
    
    if len(rules) == 0:
        return False, "Template harus memiliki minimal satu aturan"
    
    if len(rules) > 10:
        return False, "Template tidak boleh memiliki lebih dari 10 aturan"
    
    # Validate each rule
    for i, rule in enumerate(rules):
        if not isinstance(rule, str):
            return False, f"Aturan ke-{i+1} harus berupa string"
        
        if not rule.strip():
            return False, f"Aturan ke-{i+1} tidak boleh kosong"
        
        if len(rule.strip()) > 50:
            return False, f"Aturan ke-{i+1} terlalu panjang (maksimal 50 karakter)"
    
    # Check for duplicates
    if len(rules) != len(set(rules)):
        return False, "Template tidak boleh memiliki aturan yang duplikat"
    
    # Validate separator if present
    separator = template.get("pemisah", " - ")
    if not isinstance(separator, str):
        return False, "Field 'pemisah' harus berupa string"
    
    if len(separator) > 10:
        return False, "Pemisah terlalu panjang (maksimal 10 karakter)"
    
    return True, ""

def validate_templates_data(templates):
    """
    Validates the entire templates data structure.
    
    Args:
        templates (dict): Dictionary of all templates
        
    Returns:
        tuple: (is_valid: bool, error_message: str, cleaned_templates: dict)
    """
    if not isinstance(templates, dict):
        return False, "Data template harus berupa dictionary", {}
    
    cleaned_templates = {}
    errors = []
    
    for name, template in templates.items():
        # Validate template name
        if not isinstance(name, str) or not name.strip():
            errors.append(f"Nama template tidak valid: {name}")
            continue
        
        # Validate template structure
        is_valid, error_msg = validate_template_structure(template)
        if not is_valid:
            errors.append(f"Template '{name}': {error_msg}")
            continue
        
        cleaned_templates[name] = template
    
    if errors:
        return False, "; ".join(errors), cleaned_templates
    
    return True, "", cleaned_templates

def create_backup(templates):
    """
    Create a backup of current templates before making changes.
    
    Args:
        templates (dict): Current templates to backup
        
    Returns:
        str: Path to backup file created
    """
    try:
        backup_dir = get_app_data_dir() / BACKUP_DIR
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"templates_backup_{timestamp}.json"
        backup_path = backup_dir / backup_filename
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(templates, f, indent=4, ensure_ascii=False)
        
        # Clean up old backups (keep only latest MAX_BACKUP_FILES)
        cleanup_old_backups(backup_dir)
        
        return str(backup_path)
        
    except Exception as e:
        logging.error(f"Failed to create backup: {e}")
        raise ConfigError(f"Gagal membuat backup: {e}")

def cleanup_old_backups(backup_dir):
    """Remove old backup files, keeping only the latest ones."""
    try:
        backup_files = list(backup_dir.glob("templates_backup_*.json"))
        backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Remove old backups beyond the limit
        for old_backup in backup_files[MAX_BACKUP_FILES:]:
            old_backup.unlink()
            
    except Exception as e:
        logging.warning(f"Error cleaning up old backups: {e}")

def load_templates():
    """
    Memuat daftar template dari file JSON dengan validasi yang enhanced.
    
    Returns:
        dict: Dictionary of templates, empty dict if file doesn't exist or is invalid
        
    Raises:
        ConfigError: If there's a critical error in loading templates
    """
    template_file = get_template_file_path()
    
    if not template_file.exists():
        logging.info("Template file tidak ditemukan, menggunakan template kosong")
        return {}
    
    try:
        # Check file size
        file_size = template_file.stat().st_size
        if file_size == 0:
            logging.warning("Template file kosong")
            return {}
        
        # Check if file is too large (reasonable limit)
        max_size = 10 * 1024 * 1024  # 10MB
        if file_size > max_size:
            raise ConfigError(f"File template terlalu besar ({file_size} bytes)")
        
        # Load and parse JSON
        with open(template_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # Validate loaded data
        is_valid, error_msg, cleaned_templates = validate_templates_data(raw_data)
        
        if not is_valid:
            # Try to create backup of corrupted file
            try:
                corrupted_backup = template_file.with_suffix('.corrupted.json')
                shutil.copy2(template_file, corrupted_backup)
                logging.warning(f"File template rusak disimpan sebagai backup: {corrupted_backup}")
            except Exception:
                pass
            
            logging.error(f"Template file corrupt: {error_msg}")
            return cleaned_templates  # Return what we could salvage
        
        logging.info(f"Berhasil memuat {len(cleaned_templates)} template")
        return cleaned_templates
        
    except json.JSONDecodeError as e:
        logging.error(f"Template file bukan JSON valid: {e}")
        # Try to create backup of corrupted file
        try:
            corrupted_backup = template_file.with_suffix('.corrupted.json')
            shutil.copy2(template_file, corrupted_backup)
        except Exception:
            pass
        return {}
        
    except PermissionError:
        raise ConfigError(f"Tidak ada izin untuk membaca file template: {template_file}")
        
    except Exception as e:
        logging.error(f"Error loading templates: {e}")
        raise ConfigError(f"Error memuat template: {e}")

def save_templates(templates):
    """
    Menyimpan daftar template ke file JSON dengan validasi yang enhanced.
    
    Args:
        templates (dict): Dictionary of templates to save
        
    Raises:
        ConfigError: If save operation fails
        TemplateError: If template validation fails
    """
    # Validate input
    if not isinstance(templates, dict):
        raise TemplateError("Templates harus berupa dictionary")
    
    # Validate all templates
    is_valid, error_msg, cleaned_templates = validate_templates_data(templates)
    if not is_valid:
        raise TemplateError(f"Template tidak valid: {error_msg}")
    
    template_file = get_template_file_path()
    
    try:
        # Create backup before saving if file exists
        if template_file.exists():
            current_templates = load_templates()
            create_backup(current_templates)
        
        # Write to temporary file first (atomic write)
        temp_file = template_file.with_suffix('.tmp')
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_templates, f, indent=4, ensure_ascii=False)
        
        # Verify the file was written correctly
        try:
            with open(temp_file, 'r', encoding='utf-8') as f:
                verification_data = json.load(f)
            
            # Quick validation of written data
            if not isinstance(verification_data, dict):
                raise ConfigError("File yang ditulis tidak valid")
                
        except json.JSONDecodeError:
            raise ConfigError("File yang ditulis bukan JSON valid")
        
        # Atomic move (replace original with temp file)
        if os.name == 'nt':  # Windows
            if template_file.exists():
                template_file.unlink()
        
        temp_file.rename(template_file)
        
        logging.info(f"Berhasil menyimpan {len(cleaned_templates)} template")
        
    except PermissionError:
        raise ConfigError(f"Tidak ada izin untuk menulis file template: {template_file}")
        
    except OSError as e:
        raise ConfigError(f"Error sistem saat menyimpan template: {e}")
        
    except Exception as e:
        # Clean up temp file if it exists
        temp_file = template_file.with_suffix('.tmp')
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        
        logging.error(f"Error saving templates: {e}")
        raise ConfigError(f"Error menyimpan template: {e}")

def get_available_backups():
    """
    Get list of available backup files.
    
    Returns:
        list: List of backup file paths sorted by creation time (newest first)
    """
    try:
        backup_dir = get_app_data_dir() / BACKUP_DIR
        backup_files = list(backup_dir.glob("templates_backup_*.json"))
        backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return backup_files
    except Exception as e:
        logging.error(f"Error getting backup list: {e}")
        return []

def restore_from_backup(backup_path):
    """
    Restore templates from a backup file.
    
    Args:
        backup_path (str): Path to backup file
        
    Returns:
        dict: Restored templates
        
    Raises:
        ConfigError: If restore operation fails
    """
    try:
        backup_file = Path(backup_path)
        if not backup_file.exists():
            raise ConfigError(f"Backup file tidak ditemukan: {backup_path}")
        
        with open(backup_file, 'r', encoding='utf-8') as f:
            restored_templates = json.load(f)
        
        # Validate restored data
        is_valid, error_msg, cleaned_templates = validate_templates_data(restored_templates)
        if not is_valid:
            raise ConfigError(f"Backup file tidak valid: {error_msg}")
        
        # Save as current templates
        save_templates(cleaned_templates)
        
        logging.info(f"Berhasil restore dari backup: {backup_path}")
        return cleaned_templates
        
    except json.JSONDecodeError:
        raise ConfigError(f"Backup file bukan JSON valid: {backup_path}")
    except Exception as e:
        raise ConfigError(f"Error restore dari backup: {e}")