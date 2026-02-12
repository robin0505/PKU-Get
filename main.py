#!/usr/bin/env python3
"""
PKU Course Downloader - Main Entry Point
Because life is too short to click download buttons.

Usage: python main.py [config.ini]
"""
import sys
import os
import argparse
import getpass
from pathlib import Path

from pku_downloader.config import Config
from pku_downloader.browser import get_driver
from pku_downloader.auth import PKUAuth
from pku_downloader.download import Downloader
from pku_downloader.course_config import ensure_course_config
from pku_downloader.logger import setup_logger, get_logger

# Setup logger first
setup_logger(log_file='downloader.log')
logger = get_logger()


def interactive_setup():
    """
    Guide the user through creating a config file if one doesn't exist.
    Returns the path to the created config file, or None if aborted.
    """
    print("\n" + "="*60)
    print(" WELCOME TO PKU COURSE DOWNLOADER")
    print(" It seems you don't have a configuration file yet.")
    print(" Let's set one up so you don't have to do this again.")
    print("="*60 + "\n")

    try:
        choice = input("Create a new configuration now? [Y/n]: ").strip().lower()
        if choice in ('n', 'no'):
            print("Okay, exiting. Come back when you're ready.")
            return None

        print("\n--- CREDENTIALS (Required for IAAA Login) ---")
        username = input("Student ID: ").strip()
        if not username:
            print("Error: Student ID is required.")
            return None
            
        password = getpass.getpass("Password (hidden input): ").strip()
        if not password:
            print("Error: Password is required.")
            return None

        print("\n--- DOWNLOAD SETTINGS ---")
        default_dl = Config.DEFAULTS['download_dir']
        dl_input = input(f"Download Directory [{default_dl}]: ").strip()
        download_dir = str(Path(dl_input).expanduser().resolve()) if dl_input else default_dl

        # Determine save location
        save_dir = Path.home() / '.pku_downloader'
        save_dir.mkdir(exist_ok=True)
        config_path = save_dir / 'config.ini'
        
        # Determine where to save the courses.json (metadata)
        # Defaulting to alongside the config file for tidiness
        course_config_path = save_dir / 'courses.json'

        # Generate content
        content = Config.TEMPLATE.format(
            username=username,
            password=password,
            download_dir=download_dir.replace('\\', '/'), # Fix windows paths for config file
            course_config_path=str(course_config_path).replace('\\', '/')
        )

        # Write file
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"\n[Success] Configuration saved to: {config_path}")
        print(f"[Info] Course metadata will be saved to: {course_config_path}")
        print("You can edit these files later if needed.\n")
        
        return config_path

    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        return None


def main():
    """Main function. It downloads stuff. What else do you need to know?"""
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='Download PKU course materials')
    parser.add_argument('config', nargs='?', default=None, help='Path to config file')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be downloaded')
    parser.add_argument('--course', help='Download specific course by ID')
    parser.add_argument('--tabs', help='Comma-separated list of tabs to download (e.g., "教学内容,作业")')
    parser.add_argument('--all-tabs', action='store_true', help='Download all available tabs')
    args = parser.parse_args()
    
    config_file_path = args.config

    # Load config (with fallback to interactive setup)
    try:
        config = Config(config_file_path)
    except FileNotFoundError:
        if config_file_path and config_file_path != 'config.ini':
            # User specified a path that doesn't exist
            logger.error(f"ERROR: specified config file '{config_file_path}' not found.")
            return 1
        
        # Default config not found -> Run Wizard
        created_path = interactive_setup()
        if not created_path:
            return 1
        
        # Reload config with the newly created file
        try:
            config = Config(str(created_path))
        except Exception as e:
            logger.error(f"Error loading the new config: {e}")
            return 1
            
    except ValueError as e:
        logger.error(f"ERROR: Config file is invalid: {e}")
        return 1

    # Get browser driver
    logger.info(f"Starting {config.get('browser')} browser...")
    driver = None
    try:
        driver = get_driver(
            browser=config.get('browser'),
            headless=config.getbool('headless')
        )
    except Exception as e:
        logger.error(f"Failed to start browser: {e}")
        return 1
    
    try:
        # Login
        logger.info(f"Logging in as {config.get('username')}...")
        auth = PKUAuth(driver)
        session, courses, error_msg = auth.login(
            config.get('username'),
            config.get('password')
        )

        if not session:
            error_detail = error_msg if error_msg else "Login failed. Check your credentials."
            logger.error(error_detail)
            return 1

        logger.info(f"Found {len(courses)} courses")

        # Handle courses.json path
        cfg_path_val = config.get('course_config_path', 'courses.json')
        course_config_p = Path(cfg_path_val)
        
        if not course_config_p.is_absolute():
            parent_dir = config.config_path.parent
            course_config_p = parent_dir / cfg_path_val

        created, course_preferences = ensure_course_config(course_config_p, courses)

        if created:
            # --- INTERACTIVE PAUSE START ---
            logger.info(f"Created course configuration template at {course_config_p}")
            
            print("\n" + "!"*60)
            print(" NEW COURSE CONFIGURATION GENERATED ")
            print("!"*60)
            print(f"I have created a course list file at:\n  -> {course_config_p}")
            print("\nBy default, I will download ALL detected courses.")
            print("If you want to SKIP courses or RENAME them, you should edit this file.")
            print("-" * 60)
            
            choice = input("Press [Enter] to start downloading with defaults, or 'q' to quit and edit: ").strip().lower()
            
            if choice == 'q':
                logger.info("Exiting to allow configuration editing.")
                return 0
            # --- INTERACTIVE PAUSE END ---

        # Merge preferences into course entries
        for course in courses:
            prefs = course_preferences.get(course.get('id'), {})
            course.update(prefs)

        # Fetch course metadata to get available tabs
        logger.info("Fetching course metadata...")
        downloader = Downloader(session, config)
        courses = downloader.fetch_metadata(courses)
        logger.info(f"Fetched metadata for {len(courses)} courses")

        # Handle command line tab selection
        if args.all_tabs:
            # Download all available tabs
            logger.info("Command line: Downloading all available tabs")
            for course in courses:
                if 'available_tabs' in course and course['available_tabs']:
                    course['selected_tabs'] = course['available_tabs']
                    logger.info(f"  {course['name']}: {', '.join(course['available_tabs'])}")
                else:
                    logger.warning(f"No available tabs found for course {course.get('name')}")
        elif args.tabs:
            # Download specific tabs from command line
            selected_tabs_list = [tab.strip() for tab in args.tabs.split(',')]
            logger.info(f"Command line: Downloading tabs: {', '.join(selected_tabs_list)}")
            for course in courses:
                course['selected_tabs'] = selected_tabs_list
        else:
            # Use existing selected_tabs from config (may be empty)
            logger.info("Using tab selection from config file")
            for course in courses:
                selected = course.get('selected_tabs', [])
                if selected:
                    logger.info(f"  {course['name']}: {', '.join(selected)}")
                else:
                    logger.info(f"  {course['name']}: No tabs selected")

        skipped_ids = {c['id'] for c in courses if c.get('skip')}

        if driver:
            try:
                logger.debug("Closing browser after login...")
                driver.quit()
            except Exception as quit_err:
                logger.warning(f"Warning: failed to close browser cleanly: {quit_err}")
            finally:
                driver = None
        
        # Filter courses based on config
        target_courses = []
        download_mode = config.get('download_mode')
        
        if args.course:
            target_courses = [c for c in courses if c['id'] == args.course]
            if not target_courses:
                logger.error(f"Course {args.course} not found")
                return 1
        elif download_mode == 'all_current':
            target_courses = courses
        elif download_mode == 'specific':
            course_ids = {cid.strip() for cid in config.get('course_ids', '').split(',') if cid.strip()}
            target_courses = [c for c in courses if c['id'] in course_ids]

            if not target_courses and course_ids:
                logger.error(f"None of the specified courses found: {course_ids}")
                return 1

        if not args.course:
            target_courses = [c for c in target_courses if not c.get('skip')]

        if not target_courses:
            logger.warning("No courses to download. Check your config.")
            return 0

        logger.info(f"\nWill download {len(target_courses)} courses:")
        for course in target_courses:
            display_name = course.get('alias') or course.get('name')
            if display_name != course.get('name'):
                logger.info(f"  - {course['name']} -> {display_name} (ID: {course['id']})")
            else:
                logger.info(f"  - {display_name} (ID: {course['id']})")

        if args.dry_run:
            logger.info("\n--dry-run specified, exiting without downloading")
            return 0

        # Download courses
        downloader = Downloader(session, config)
        downloader.download_courses(target_courses)

        downloader.print_stats()
        logger.info("\nDone. Your files are downloaded. Now go study.")
        return 0

    except KeyboardInterrupt:
        logger.warning("\n\nCancelled by user.")
        return 130
    except Exception as e:
        logger.error(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if driver:
            driver.quit()


if __name__ == '__main__':
    sys.exit(main())