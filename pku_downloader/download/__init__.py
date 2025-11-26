"""
Downloader - The actual work happens here.
No BS, just download files efficiently.
"""
import re
import time
import json
import requests
import mimetypes
import traceback
from collections import namedtuple
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from ..logger import get_logger

logger = get_logger('download')


class Downloader:
    """Download files from PKU's course system. It's not pretty but it works."""
    
    COMMON_EXTENSIONS = [
        '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
        '.zip', '.rar', '.7z', '.tar', '.gz',
        '.txt', '.md', '.ipynb',
        '.jpg', '.jpeg', '.png', '.gif', '.swf',
        '.mp4', '.avi', '.mov', '.wmv', '.mpg', '.mpeg',
        '.mp3', '.wav', '.ogg'
    ]

    # Simple magic-signature based detection (fast, no extra deps)
    MagicHit = namedtuple('MagicHit', ['mime', 'ext'])
    MAGIC_PREFIXES: Dict[bytes, MagicHit] = {
        b"%PDF-": MagicHit('application/pdf', '.pdf'),
        b"PK\x03\x04": MagicHit('application/zip', '.zip'),  # also docx/pptx/xlsx containers
        b"Rar!": MagicHit('application/x-rar-compressed', '.rar'),
        b"7z\xBC\xAF\x27\x1C": MagicHit('application/x-7z-compressed', '.7z'),
        b"\x1F\x8B\x08": MagicHit('application/gzip', '.gz'),
        b"\x89PNG\r\n\x1a\n": MagicHit('image/png', '.png'),
        b"\xff\xd8\xff": MagicHit('image/jpeg', '.jpg'),
        b"GIF87a": MagicHit('image/gif', '.gif'),
        b"GIF89a": MagicHit('image/gif', '.gif'),
        b"ID3": MagicHit('audio/mpeg', '.mp3'),
        b"\x00\x00\x00\x18ftyp": MagicHit('video/mp4', '.mp4'),
        b"ftypisom": MagicHit('video/mp4', '.mp4'),
        b"ftypmp42": MagicHit('video/mp4', '.mp4'),
    }

    def _guess_from_magic(self, head: bytes) -> Optional[Tuple[str, str]]:
        """Return (mime, ext) if a known magic prefix matches."""
        for sig, hit in self.MAGIC_PREFIXES.items():
            if head.startswith(sig):
                return hit.mime, hit.ext
        return None

    def _choose_extension(self, filename: str, content_type: Optional[str], head: Optional[bytes]) -> Optional[Tuple[str, str, Optional[str]]]:
        """Decide a better extension for filename based on headers and magic.
        Returns a tuple (ext, source, mime) or None if we shouldn't change it.
        """
        # If filename already has a plausible extension, keep it
        base = filename.rsplit('/', 1)[-1]
        if '.' in base and base.lower().endswith(tuple(self.COMMON_EXTENSIONS)):
            return None

        # Try HTTP Content-Type
        if content_type and content_type != 'application/octet-stream':
            # Normalize and map to extension
            ext = mimetypes.guess_extension(content_type.split(';', 1)[0].strip())
            # Fix common None cases
            if not ext and content_type.startswith('image/jpeg'):
                ext = '.jpg'
            if ext:
                return (ext, 'content-type', content_type.split(';', 1)[0].strip())

        # Try magic bytes
        if head:
            hit = self._guess_from_magic(head)
            if hit:
                return (hit[1], 'magic', self._guess_from_magic(head)[0] if self._guess_from_magic(head) else None)

        # Heuristic for OOXML inside zip
        if head and head.startswith(b"PK\x03\x04"):
            # Don't force .zip — let original name stand if text hints exist
            return ('.zip', 'zip-heuristic', None)

        return None

    def _has_known_extension(self, name: str) -> bool:
        """Return True if name ends with a known extension from COMMON_EXTENSIONS."""
        base = name.rsplit('/', 1)[-1].lower()
        return any(base.endswith(ext) for ext in self.COMMON_EXTENSIONS)

    def _existing_extension(self, name: str) -> Optional[str]:
        """Return the suffix found in name (e.g., '.pdf') if present and plausible; else None.
        Plausible = dot + 2~6 alnum chars (covers most common cases like .pdf/.pptx/.mpeg etc.).
        """
        try:
            ext = Path(name).suffix
        except Exception:
            ext = ''
        ext = (ext or '').strip().lower()
        if ext and 2 <= len(ext) <= 6 and re.fullmatch(r'\.[a-z0-9]+', ext):
            return ext
        return None

    def _filename_from_headers(self, content_disp: Optional[str]) -> Optional[str]:
        """Extract filename from Content-Disposition header if present."""
        if not content_disp:
            return None
        try:
            match = re.search(r"filename\*=utf-8''([^;]+)", content_disp, re.IGNORECASE)
            if match:
                return unquote(match.group(1))
            match = re.search(r'filename=([^;]+)', content_disp, re.IGNORECASE)
            if match:
                return unquote(match.group(1).strip('"\''))
        except Exception:
            pass
        return None
    
    def __init__(self, session: requests.Session, config):
        self.session = session
        self.config = config
        self.stats = {'downloaded': 0, 'skipped': 0, 'failed': 0}

        # Sync report tracking
        self.sync_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.started_at = datetime.now()
        self.file_records = {
            'downloaded': [],
            'skipped': [],
            'failed': []
        }

        # Track current course directory for relative path recording
        self.current_course_dir = None

        # Ensure reports directory exists
        config_dir = Path(config.config_path).parent if hasattr(config, 'config_path') else Path.home() / '.pku_downloader'
        self.reports_dir = config_dir / 'reports'
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Progress tracking
        self.progress = {
            'phase': 'idle',
            'total_courses': 0,
            'current_course_index': 0,
            'current_course_name': '',
            'course_files_total': 0,
            'course_files_done': 0,
            'current_file_name': '',
            'current_file_progress': 0.0,
            'current_file_size': 0,
            'current_file_downloaded': 0
        }
        self.last_progress_update = 0
        self.window = None  # Will be set by gui.py

    def get_course_tabs(self, course: Dict) -> List[Dict]:
        """Fetch available tabs for a single course without downloading content."""
        course_url = course.get('url')
        if not course_url:
            return []

        try:
            response = self.session.get(course_url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            menu = soup.find('ul', id='courseMenuPalette_contents')
            if not menu:
                return []

            # Use _find_content_areas but force download_all=True to get EVERYTHING
            # We want to discover all possibilities, not just what's configured
            original_config_val = self.config.config.get('DEFAULT', 'download_all_areas', fallback='false')

            # Temporarily mock config to get all areas
            # Note: This is a bit hacky but avoids rewriting _find_content_areas signature
            # A cleaner way would be to pass a flag to _find_content_areas
            areas = []
            for link in menu.find_all('a'):
                name = link.text.strip()
                url = link.get('href')

                if not url or url.startswith('#') or url.startswith('javascript:'):
                    continue

                # We only care about content areas usually
                # But let's just grab everything that looks like a content link
                areas.append({
                    'name': name,
                    'url': urljoin(response.url, url),
                    'flatten': course.get('flatten', True)
                })
            return areas

        except Exception as e:
            logger.error(f"Failed to fetch tabs for {course.get('name')}: {e}")
            return []

    def _emit_progress(self):
        """Emit progress update to frontend (throttled to 100ms)"""
        now = time.time()
        if now - self.last_progress_update < 0.1:  # 100ms throttle
            return

        self.last_progress_update = now

        if self.window:
            try:
                progress_data = {
                    **self.progress,
                    'stats': self.stats.copy()
                }
                self.window.evaluate_js(
                    f"if(window.updateProgress) window.updateProgress({json.dumps(progress_data)})"
                )
            except Exception as e:
                logger.debug(f"Failed to emit progress: {e}")

    def fetch_metadata(self, courses: List[Dict]) -> List[Dict]:
        """
        Parallel fetch of tabs for all courses.
        Returns the courses list enriched with a 'tabs' key.
        """
        logger.info("Fetching course metadata...")
        
        def _enrich_course(course):
            # Return a new dict to avoid modifying the original in place if that matters,
            # but here we just modify and return.
            # We need to clone it to avoid race conditions if any
            c_copy = course.copy()
            c_copy['tabs'] = self.get_course_tabs(c_copy)
            # Extract just the names for the UI
            c_copy['available_tabs'] = [t['name'] for t in c_copy['tabs']]
            return c_copy

        enriched_courses = []
        # Use parallel execution to speed up metadata fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_enrich_course, c): c for c in courses}
            for future in as_completed(futures):
                try:
                    enriched_courses.append(future.result())
                except Exception as e:
                    logger.error(f"Error enriching course: {e}")
                    # Return original course if enrichment fails
                    enriched_courses.append(courses[futures[future]])
        
        return enriched_courses
    
    def download_courses(self, courses: List[Dict]):
        """Download content from multiple courses."""
        self.current_course_name = None  # Track current course for error reporting
        self.current_course_id = None  # Track current course ID for reports
        self.progress['total_courses'] = len(courses)
        self.progress['phase'] = 'downloading'
        self._emit_progress()

        try:
            for idx, course in enumerate(courses):
                self.progress['current_course_index'] = idx + 1
                self.download_course(course)
        finally:
            # Always generate report, even if interrupted
            self.progress['phase'] = 'complete'
            self._emit_progress()
            self.generate_report()

    def download_course(self, course: Dict):
        """Download all content from a course."""
        course_id = course.get('id', 'unknown')
        raw_name = course.get('alias') or course.get('name', f'Course_{course_id}')
        course_name = self._sanitize_name(raw_name)
        self.current_course_name = course_name  # Track for error reporting
        self.current_course_id = course_id  # Track for reports

        # Create course directory and track it for relative path recording
        course_dir = Path(self.config.get('download_dir')) / course_name
        course_dir.mkdir(parents=True, exist_ok=True)
        self.current_course_dir = course_dir

        # Update progress
        self.progress['current_course_name'] = course_name
        self.progress['course_files_done'] = 0
        self.progress['course_files_total'] = 0  # Will be updated as we discover files
        self._emit_progress()

        course_url = course.get('url')

        if not course_url:
            logger.warning(f"No URL for course {course_name}")
            return

        logger.info(f"\n=== Downloading: {course_name} ===")

        # Get course page and find content areas
        try:
            # 🔑 使用已有的 tabs 数据（来自 fetch_metadata）
            # 如果没有，才重新获取
            if 'tabs' in course and course['tabs']:
                content_areas = course['tabs']
            else:
                content_areas = self.get_course_tabs(course)

            if not content_areas:
                logger.warning(f"No content areas found for {course_name}")
                return

            # 🔑 根据 selected_tabs 过滤要下载的区域
            selected_tabs = course.get('selected_tabs', [])
            
            if selected_tabs:
                # 用户有明确选择 - 只处理选中的标签页
                filtered_areas = [area for area in content_areas if area['name'] in selected_tabs]
                if filtered_areas:
                    logger.info(f"  Selected tabs: {', '.join(selected_tabs)}")
                    content_areas = filtered_areas
                else:
                    logger.warning(f"No matching tabs found for selected: {selected_tabs}")
                    return
            else:
                # 用户没有选择任何标签页 - 跳过下载
                logger.info(f"  No tabs selected, skipping download")
                return

            for area in content_areas:
                area_name = self._sanitize_name(area['name'])
                if area.get('flatten'):
                    area_dir = course_dir
                else:
                    area_dir = course_dir / area_name
                    area_dir.mkdir(parents=True, exist_ok=True)

                logger.info(f"\n  Processing: {area_name}")
                
                # Check for notification/announcement tab
                if "公告" in area_name or "通知" in area_name or "Announcements" in area_name:
                    self._process_notifications(area['url'], area_dir)
                else:
                    self._process_content_area(area['url'], area_dir)

        except requests.RequestException as e:
            logger.error(f"Network error processing course {course_name}: {e}")
        except Exception as e:
            logger.error(f"Failed to process course {course_name}: {e}")
    
    def _find_content_areas(self, menu, base_url: str, course: Dict) -> List[Dict]:
        """Find content areas to download from."""
        areas = []
        download_all = self.config.getbool('download_all_areas')
        target_areas = set()

        course_sections = course.get('sections')
        course_sections_set = set(course_sections) if course_sections else set()

        if course_sections and '*' in course_sections:
            download_all = True
        elif course_sections_set:
            target_areas = course_sections_set
        elif not download_all:
            locations = self.config.get('default_content_locations', '教学内容')
            target_areas = {name.strip() for name in locations.split(',') if name.strip()}

        for link in menu.find_all('a'):
            name = link.text.strip()
            url = link.get('href')

            if not url or url.startswith('#') or url.startswith('javascript:'):
                continue

            if download_all or name in target_areas:
                areas.append({
                    'name': name,
                    'url': urljoin(base_url, url),
                    'flatten': course.get('flatten', True)
                })

        return areas
    
    def _process_content_area(self, url: str, local_dir: Path):
        """Process a content area (handles pagination)."""
        current_url = url
        processed_folders = set()
        
        while current_url:
            try:
                response = self.session.get(current_url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find content list
                content_list = soup.find('ul', id='content_listContainer')
                if not content_list:
                    content_list = soup.select_one('div.container-fluid ul.listElement')
                
                if content_list:
                    self._process_content_list(content_list, response.url, local_dir, processed_folders)
                
                # Check for next page
                next_link = soup.find('a', title='下一页')
                if next_link and next_link.get('href'):
                    next_url = urljoin(response.url, next_link['href'])
                    if next_url != current_url:
                        current_url = next_url
                        time.sleep(0.5)  # Be nice to the server
                    else:
                        current_url = None
                else:
                    current_url = None

            except requests.RequestException as e:
                logger.error(f"    Network error processing content area: {e}")
                current_url = None
            except Exception as e:
                logger.error(f"    Error processing content area: {e}")
                current_url = None
    
    def _process_content_list(self, content_list, base_url: str, local_dir: Path, processed_folders: set):
        """Process links in content list."""
        links = content_list.find_all('a', href=True)
        
        # Use thread pool for concurrent downloads
        max_workers = self.config.getint('concurrent_downloads', 3)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []

            for link in links:
                href = link.get('href', '')
                text = link.text.strip()

                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue

                full_url = urljoin(base_url, href)

                # Check if it's a folder
                if self._is_folder(link, href):
                    folder_name = self._sanitize_name(text or "Unnamed_Folder")
                    if full_url not in processed_folders:
                        processed_folders.add(full_url)
                        folder_dir = local_dir / folder_name
                        folder_dir.mkdir(parents=True, exist_ok=True)
                        # Recursively process folder
                        self._process_content_area(full_url, folder_dir)
                    continue

                # Check if it's a file
                if self._is_file(link, href, text):
                    filename = self._extract_filename(href, text)
                    if filename:
                        file_path = local_dir / filename
                        future = executor.submit(self._download_file, full_url, file_path, text)
                        futures.append(future)

            # Wait for downloads to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.debug(f"      Download error: {e}")
    
    def _is_folder(self, link, href: str) -> bool:
        """Check if link is a folder."""
        if 'listContent.jsp' in href or 'listContentEditable.jsp' in href:
            return True
        
        parent_li = link.find_parent('li')
        if parent_li:
            classes = parent_li.get('class', [])
            if 'folder' in classes:
                return True
            
            img = parent_li.find('img')
            if img and 'folder' in img.get('src', '').lower():
                return True
        
        return False
    
    def _is_file(self, link, href: str, text: str) -> bool:
        """Check if link is a downloadable file."""
        # Direct file links
        if '/bbcswebdav/' in href:
            return True
        
        # Check extensions
        href_lower = href.lower().split('?')[0]
        if any(href_lower.endswith(ext) for ext in self.COMMON_EXTENSIONS):
            return True
        
        # Check text for extensions
        if text and any(text.lower().endswith(ext) for ext in self.COMMON_EXTENSIONS):
            return True
        
        # Download links
        if any(marker in href for marker in ['download', 'attachFile', 'downloadFile']):
            return True
        
        return False
    
    def _extract_filename(self, href: str, text: str) -> str:
        """Extract filename from URL or text."""
        filename = None

        # 1) Prefer link text as the displayed/download name
        if text and text.strip():
            filename = text.strip()

        # 2) If no usable text, try to get from URL path
        if not filename:
            if '/bbcswebdav/' in href:
                try:
                    path_part = href.split('/bbcswebdav/', 1)[1].split('?')[0]
                    filename = unquote(path_part.split('/')[-1])
                except Exception:
                    pass

        # 3) If still not found, use URL tail
        if not filename:
            try:
                filename = unquote(href.split('/')[-1].split('?')[0])
            except Exception:
                pass

        # 4) Generate fallback name
        if not filename:
            filename = f"download_{int(time.time()*1000)}"

        return self._sanitize_name(filename)
    
    def _download_file(self, url: str, file_path: Path, link_text: Optional[str] = None) -> bool:
        """Download a single file."""
        # Update progress - starting new file
        self.progress['current_file_name'] = link_text or file_path.name
        self.progress['current_file_progress'] = 0.0
        self.progress['current_file_size'] = 0
        self.progress['current_file_downloaded'] = 0
        self.progress['course_files_total'] += 1
        self._emit_progress()

        # Determine overwrite behavior and preflight HEAD
        overwrite_mode = self.config.get('overwrite', 'size')
        remote_size = -1
        head_ct = None
        try:
            head_resp = self.session.head(url, timeout=10, allow_redirects=True)
            remote_size = int(head_resp.headers.get('Content-Length', -1))
            head_ct = head_resp.headers.get('Content-Type')
            self.progress['current_file_size'] = remote_size
        except Exception:
            pass

        # Always prefer link text as the base name for saving
        base_name = self._sanitize_name(link_text) if link_text else file_path.stem
        existing_ext = self._existing_extension(base_name)

        # If text has an extension, DO NOT infer/append here; keep the text as-is.
        if existing_ext:
            tentative_name = base_name
        else:
            # If text has no extension, try to infer from HEAD Content-Type
            if head_ct and head_ct != 'application/octet-stream':
                ext_from_head = mimetypes.guess_extension(head_ct.split(';', 1)[0].strip())
                if not ext_from_head and head_ct.startswith('image/jpeg'):
                    ext_from_head = '.jpg'
            else:
                ext_from_head = None
            tentative_name = base_name + (ext_from_head or '')
        file_path = file_path.with_name(tentative_name)

        # Overwrite/skip decision using preflight info
        if file_path.exists():
            if overwrite_mode == 'never':
                self.stats['skipped'] += 1
                self.progress['course_files_done'] += 1
                self._record_file('skipped', file_path.name, reason='already_exists', file_path=file_path)
                self._emit_progress()
                return False
            elif overwrite_mode == 'size' and remote_size > -1:
                try:
                    if file_path.stat().st_size == remote_size:
                        self.stats['skipped'] += 1
                        self.progress['course_files_done'] += 1
                        logger.info(f"      [SKIP] (same size): {file_path.name}")
                        self._record_file('skipped', file_path.name, reason='same_size', size=remote_size, file_path=file_path)
                        self._emit_progress()
                        return False
                except Exception:
                    pass

        # Download the file
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            response = self.session.get(url, stream=True, timeout=180)
            response.raise_for_status()

            # Possibly refine filename using headers first
            content_disp = response.headers.get('content-disposition')
            header_name = self._filename_from_headers(content_disp)
            if header_name:
                file_path = file_path.with_name(self._sanitize_name(header_name))

            # Get actual file size from response
            total_size = int(response.headers.get('Content-Length', 0))
            self.progress['current_file_size'] = total_size
            downloaded = 0

            # Read first chunk to sniff content (but also write it later)
            iterator = response.iter_content(chunk_size=8192)
            try:
                first_chunk = next(iterator)
            except StopIteration:
                first_chunk = b''

            # If and only if the original link text lacked an extension, try to choose a better extension
            text_has_ext = bool(self._existing_extension(link_text or ''))
            if not text_has_ext:
                chosen = self._choose_extension(file_path.name, response.headers.get('Content-Type'), first_chunk)
                if chosen:
                    ext, source, mime = chosen
                    detail = f" MIME={mime}" if mime else ""
                    logger.debug(f"      [infer] '{link_text or file_path.stem}' -> add {ext} via {source}.{detail}")
                    stem = file_path.stem
                    new_path = file_path.with_name(self._sanitize_name(stem + ext))

                    # If the final-target file already exists and matches remote size, skip
                    try:
                        resp_size = int(response.headers.get('Content-Length', -1))
                    except Exception:
                        resp_size = -1
                    if new_path.exists() and resp_size > -1:
                        try:
                            if new_path.stat().st_size == resp_size:
                                self.stats['skipped'] += 1
                                self.progress['course_files_done'] += 1
                                logger.info(f"      [SKIP] (same size): {new_path.name}")
                                self._record_file('skipped', new_path.name, reason='same_size', size=resp_size, file_path=new_path)
                                self._emit_progress()
                                return True
                        except Exception:
                            pass

                    file_path = new_path

            # Write file (including the sniffed first chunk)
            with open(file_path, 'wb') as f:
                if first_chunk:
                    f.write(first_chunk)
                    downloaded += len(first_chunk)
                    if total_size > 0:
                        self.progress['current_file_progress'] = downloaded / total_size
                        self.progress['current_file_downloaded'] = downloaded
                        self._emit_progress()

                for chunk in iterator:
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Update progress
                        if total_size > 0:
                            self.progress['current_file_progress'] = downloaded / total_size
                            self.progress['current_file_downloaded'] = downloaded
                            self._emit_progress()

            logger.info(f"      [OK] {file_path.name}")
            self.stats['downloaded'] += 1
            self.progress['course_files_done'] += 1
            final_size = file_path.stat().st_size
            self._record_file('downloaded', file_path.name, size=final_size, url=url, file_path=file_path)
            self._emit_progress()
            return True

        except requests.RequestException as e:
            logger.warning(f"      [FAIL] {file_path.name}: {str(e)[:50]}")
            self.stats['failed'] += 1
            self.progress['course_files_done'] += 1
            self._record_file('failed', file_path.name, error=str(e), error_type='NetworkError', file_path=file_path)
            self._emit_progress()

            # Clean up partial download
            if file_path.exists() and file_path.stat().st_size == 0:
                file_path.unlink()

            return False
        except Exception as e:
            logger.error(f"      [FAIL] {file_path.name}: {str(e)[:50]}")
            self.stats['failed'] += 1
            self.progress['course_files_done'] += 1
            self._record_file('failed', file_path.name, error=str(e), error_type='UnknownError', traceback=traceback.format_exc(), file_path=file_path)
            self._emit_progress()

            # Clean up partial download
            if file_path.exists() and file_path.stat().st_size == 0:
                file_path.unlink()

            return False
    
    def _parse_content_disposition(self, content_disp: str) -> Optional[str]:
        """Parse filename from Content-Disposition header.
        (Kept for backward-compatibility; new code uses _filename_from_headers.)
        """
        try:
            # Try UTF-8 encoded filename
            match = re.search(r"filename\*=utf-8''([^;]+)", content_disp, re.IGNORECASE)
            if match:
                return unquote(match.group(1))
            
            # Try regular filename
            match = re.search(r'filename=([^;]+)', content_disp, re.IGNORECASE)
            if match:
                filename = match.group(1).strip('"\'')
                return unquote(filename)
        except Exception:
            pass
        
        return None
    
    def _sanitize_name(self, name: str) -> str:
        """Make a name safe for filesystem."""
        # Remove invalid characters
        name = re.sub(r'[\\/*?:"<>|\r\n]+', '', name)
        name = name.strip('. ')
        
        # Ensure non-empty
        if not name:
            name = f"unnamed_{int(time.time()*1000)}"
        
        # Truncate if too long
        if len(name) > 200:
            name = name[:200]
        
        return name
    
    def print_stats(self):
        """Print download statistics."""
        logger.info(f"\n=== Download Statistics ===")
        logger.info(f"Downloaded: {self.stats['downloaded']}")
        logger.info(f"Skipped:    {self.stats['skipped']}")
        logger.info(f"Failed:     {self.stats['failed']}")
        logger.info(f"Total:      {sum(self.stats.values())}")

    def _record_file(self, status: str, filename: str, **kwargs):
        """Record file information for sync report."""
        # If we have a course directory context, calculate relative path
        # to properly handle nested folders
        if self.current_course_dir and kwargs.get('file_path'):
            try:
                file_path = Path(kwargs['file_path'])
                relative_path = file_path.relative_to(self.current_course_dir)
                filename = str(relative_path).replace('\\', '/')  # Normalize to forward slashes
            except (ValueError, Exception):
                # If relative path calculation fails, fall back to just the filename
                pass

        record = {
            'name': filename,
            'course': self.current_course_name or 'Unknown',
            'course_id': self.current_course_id or 'unknown'
        }

        # Add optional fields
        if 'size' in kwargs:
            record['size'] = kwargs['size']
        if 'url' in kwargs:
            record['url'] = kwargs['url']
        if 'reason' in kwargs:
            record['reason'] = kwargs['reason']
        if 'error' in kwargs:
            record['error'] = kwargs['error']
        if 'error_type' in kwargs:
            record['error_type'] = kwargs['error_type']
        if 'traceback' in kwargs:
            record['traceback'] = kwargs['traceback']

        self.file_records[status].append(record)

    def generate_report(self):
        """Generate sync report and save to reports directory."""
        try:
            finished_at = datetime.now()

            report = {
                'sync_id': self.sync_id,
                'started_at': self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                'finished_at': finished_at.strftime("%Y-%m-%d %H:%M:%S"),
                'duration_seconds': int((finished_at - self.started_at).total_seconds()),
                'status': 'success' if self.stats['failed'] == 0 else 'partial_failure',
                'files': self.file_records,
                'summary': self.stats
            }

            report_path = self.reports_dir / f'{self.sync_id}.json'
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            logger.info(f"\nSync report saved to: {report_path}")
            return report_path

        except Exception as e:
            logger.error(f"Failed to generate sync report: {e}")
            return None

    def _process_notifications(self, url: str, local_dir: Path):
        """Process announcements/notifications and save as Markdown."""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to find announcement list (Standard Blackboard structure)
            container = soup.find('ul', id='announcementList')
            if not container:
                # Fallback for some customized themes
                container = soup.find('div', id='announcementList')
            
            if not container:
                logger.warning(f"    No announcement list found at {url}")
                return

            items = container.find_all('li', recursive=False)
            if not items:
                logger.info("    No announcements found.")
                return

            local_dir.mkdir(parents=True, exist_ok=True)
            count = 0

            for item in items:
                # 1. Extract Title
                title_elem = item.find('h3')
                if not title_elem:
                    # Sometimes it's just a div or span with a specific class
                    title_elem = item.find('div', class_='item_header')
                
                title = title_elem.get_text(strip=True) if title_elem else "Untitled"
                
                # 2. Extract Metadata (Date, Author)
                meta_info = []
                details = item.find('div', class_='details')
                date_str = ""
                if details:
                    # Text like: "发布时间: 2025年11月15日 星期六 上午09时47分03秒 CST"
                    full_meta = details.get_text(strip=True)
                    meta_info.append(full_meta)
                    
                    # Try to extract a clean date for filename
                    # Look for YYYY-MM-DD or YYYY年MM月DD日
                    date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', full_meta)
                    if date_match:
                        date_str = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"
                    else:
                        # Fallback to current time if date parsing fails
                        date_str = datetime.now().strftime("%Y-%m-%d")

                # 3. Extract Content
                # Content is usually in a div following the header/details, often with no class or 'vtbegenerated'
                # We'll look for the container that holds the actual message
                content_html = ""
                # Blackboard often puts content in a div with id starting with 'announcementMsg_'
                msg_div = item.find('div', id=re.compile(r'^announcementMsg_'))
                if not msg_div:
                    # Fallback: look for any div that looks like content
                    pass
                
                if msg_div:
                    # Convert HTML to basic Markdown-ish text
                    content_text = msg_div.get_text('\n', strip=True)
                    
                    # Also try to find links/attachments in the message
                    links = msg_div.find_all('a', href=True)
                    attachments = []
                    for link in links:
                        href = link['href']
                        text = link.get_text(strip=True)
                        full_link = urljoin(url, href)
                        attachments.append(f"[{text}]({full_link})")
                    
                    if attachments:
                        content_text += "\n\n### Attachments\n" + "\n".join(f"- {a}" for a in attachments)
                else:
                    content_text = "[Could not extract content]"

                # 4. Save as Markdown
                safe_title = self._sanitize_name(title)
                filename = f"{date_str}_{safe_title}.md"
                file_path = local_dir / filename
                
                md_content = f"# {title}\n\n"
                if meta_info:
                    md_content += f"> {' | '.join(meta_info)}\n\n"
                md_content += content_text
                
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(md_content)
                    count += 1
                    logger.info(f"      [NOTE] Saved: {filename}")
                except Exception as e:
                    logger.error(f"      Failed to save notification {filename}: {e}")

            if count > 0:
                logger.info(f"    Saved {count} notifications.")

        except Exception as e:
            logger.error(f"    Error processing notifications at {url}: {e}")
