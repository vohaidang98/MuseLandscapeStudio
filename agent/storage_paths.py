"""All substantial application files default to the user's requested D drive."""
import os
from pathlib import Path

HOME = Path(os.environ.get('MUSE_STUDIO_HOME', r'D:\Code\MuseLandscapeStudio'))
DATA = Path(os.environ.get('FRAMEWEAVER_DATA_DIR', HOME / 'Data'))
VIDEOS = Path(os.environ.get('MUSE_STUDIO_OUTPUT_DIR', r'D:\video'))
TEMP = DATA / 'Temp'
