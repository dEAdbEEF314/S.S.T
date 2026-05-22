import struct
import logging
from pathlib import Path
from typing import Dict, Any, List
import vdf

logger = logging.getLogger("scout.steam_vdf")

def read_null_terminated_string(f) -> str:
    chars = []
    while True:
        c = f.read(1)
        if not c or c == b'\x00':
            break
        chars.append(c)
    return b"".join(chars).decode('utf-8', errors='replace')

class SteamBinaryVDF:
    """Parses Steam's binary VDF files, specifically appinfo.vdf."""
    
    @staticmethod
    def parse_appinfo(filepath: Path) -> Dict[int, Dict[str, Any]]:
        if not filepath.exists():
            logger.error(f"appinfo.vdf not found at {filepath}")
            return {}

        try:
            with open(filepath, 'rb') as f:
                # 1. Read Header
                magic = struct.unpack('<I', f.read(4))[0]
                universe = struct.unpack('<I', f.read(4))[0]
                
                # Support Version 41 (0x07564429) and Version 29 (0x07564428)
                is_v41 = (magic == 0x07564429)
                is_v29 = (magic == 0x07564428)
                
                if not (is_v41 or is_v29):
                    logger.warning(f"Unsupported appinfo version: {hex(magic)}. Attempting best-effort parse.")
                
                string_table = []
                if is_v41:
                    string_table_offset = struct.unpack('<Q', f.read(8))[0]
                    current_pos = f.tell()
                    f.seek(string_table_offset)
                    num_strings = struct.unpack('<I', f.read(4))[0]
                    for _ in range(num_strings):
                        string_table.append(read_null_terminated_string(f))
                    f.seek(current_pos)

                apps = {}
                while True:
                    app_id_bytes = f.read(4)
                    if not app_id_bytes or app_id_bytes == b'\x00\x00\x00\x00':
                        break
                        
                    app_id = struct.unpack('<I', app_id_bytes)[0]
                    size = struct.unpack('<I', f.read(4))[0]
                    info_state = struct.unpack('<I', f.read(4))[0]
                    last_updated = struct.unpack('<I', f.read(4))[0]
                    pics_token = struct.unpack('<Q', f.read(8))[0]
                    sha1_hash = f.read(20)
                    change_number = struct.unpack('<I', f.read(4))[0]
                    
                    if is_v29 or is_v41:
                        binary_sha1 = f.read(20)
                    
                    # Parse the actual KV data
                    vdf_data = SteamBinaryVDF._parse_kv(f, string_table)
                    
                    # Simplify the structure for SST usage
                    app_data = vdf_data.get("appinfo", {})
                    if not app_data: # Sometimes it's nested differently or just the root
                        app_data = vdf_data
                    
                    apps[app_id] = app_data
                    
                return apps
        except Exception as e:
            logger.error(f"Failed to parse appinfo.vdf: {e}", exc_info=True)
            return {}

    @staticmethod
    def _parse_kv(f, string_table: List[str]) -> Dict[str, Any]:
        data = {}
        while True:
            type_byte = f.read(1)
            if not type_byte or type_byte == b'\x08': # End of object
                break
            
            # Read Key
            if string_table:
                key_index = struct.unpack('<I', f.read(4))[0]
                key = string_table[key_index]
            else:
                key = read_null_terminated_string(f)
            
            # Read Value based on type
            if type_byte == b'\x00': # Sub-section
                data[key] = SteamBinaryVDF._parse_kv(f, string_table)
            elif type_byte == b'\x01': # String
                data[key] = read_null_terminated_string(f)
            elif type_byte == b'\x02': # Int32
                data[key] = struct.unpack('<i', f.read(4))[0]
            elif type_byte == b'\x03': # Float32
                data[key] = struct.unpack('<f', f.read(4))[0]
            elif type_byte == b'\x07': # Int64
                data[key] = struct.unpack('<q', f.read(8))[0]
            elif type_byte == b'\x09': # UInt64
                data[key] = struct.unpack('<Q', f.read(8))[0]
            # Add other types if encountered (Int64, Pointer, etc.)
        return data

class SteamLibraryDiscovery:
    """Discovers Steam libraries via libraryfolders.vdf."""
    
    @staticmethod
    def discover(install_path: Path) -> List[Path]:
        lf_path = install_path / "steamapps" / "libraryfolders.vdf"
        if not lf_path.exists():
            logger.warning(f"libraryfolders.vdf not found at {lf_path}")
            return []
            
        try:
            with open(lf_path, "r", encoding="utf-8") as f:
                data = vdf.load(f)
            
            folders = []
            # libraryfolders.vdf structure:
            # "libraryfolders" { "0" { "path" "..." }, "1" { "path" "..." } }
            root = data.get("libraryfolders", {})
            for key, entry in root.items():
                if isinstance(entry, dict) and "path" in entry:
                    folders.append(entry["path"])
            return folders
        except Exception as e:
            logger.error(f"Failed to parse libraryfolders.vdf: {e}")
            return []
