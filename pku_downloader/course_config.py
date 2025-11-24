"""
Course configuration management.
Creates and maintains per-course preferences such as aliasing, skip flags,
content sections, and directory structure options.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple, Any

from .logger import get_logger

logger = get_logger('course_config')

DEFAULT_SECTIONS = ["教学内容"]
DEFAULT_FLATTEN = True


def _default_entry(course: Dict[str, Any]) -> Dict[str, Any]:
    # 🔑 默认 selected_tabs：优先选择"教学内容"，如果没有则为空
    available_tabs = course.get("available_tabs", [])
    default_tabs = ["教学内容"] if "教学内容" in available_tabs else []
    
    return {
        "name": course.get("name", ""),
        "alias": "",
        "skip": False,
        "sections": list(DEFAULT_SECTIONS),
        "flatten": DEFAULT_FLATTEN,
        "selected_tabs": default_tabs,  # GUI 需要的字段
    }


def _normalise_sections(value: Any) -> List[str]:
    if isinstance(value, list):
        sections = [str(item).strip() for item in value if str(item).strip()]
        return sections or list(DEFAULT_SECTIONS)
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(',') if part.strip()]
        return parts or list(DEFAULT_SECTIONS)
    return list(DEFAULT_SECTIONS)


def ensure_course_config(config_path: Path, courses: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Dict[str, Any]]]:
    """Ensure a course configuration file exists and is in sync with the live course list."""
    created = False
    data: Dict[str, Dict[str, Any]] = {}

    if config_path.exists():
        try:
            with config_path.open('r', encoding='utf-8') as fp:
                payload = json.load(fp)
            if isinstance(payload, dict) and isinstance(payload.get('courses'), dict):
                data = payload['courses']
            else:
                data = {}
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in course config: {e}")
            data = {}
        except OSError as e:
            logger.warning(f"Failed to read course config: {e}")
            data = {}
    else:
        created = True

    normalised: Dict[str, Dict[str, Any]] = {}

    for course in courses:
        course_id = course.get('id')
        if not course_id:
            continue
        entry = data.get(course_id, {}).copy()

        if not entry:
            # 首次创建：使用默认配置
            entry = _default_entry(course)
        else:
            # 已存在：合并配置
            defaults = _default_entry(course)
            # Preserve user choices but ensure defaults exist
            for key, value in defaults.items():
                if key not in entry:
                    entry[key] = value
            # Always keep the latest course name for reference
            if entry.get('name') != course.get('name'):
                entry['name'] = course.get('name')
            
            # 🔑 处理 selected_tabs：智能合并逻辑
            available_tabs = course.get('available_tabs', [])
            saved_tabs = entry.get('selected_tabs', None)
            
            if saved_tabs is None:
                # 从未设置过 - 使用默认值（优先"教学内容"）
                entry['selected_tabs'] = ["教学内容"] if "教学内容" in available_tabs else []
            elif isinstance(saved_tabs, list) and len(saved_tabs) == 0:
                # 用户明确清空了（保持为空）
                entry['selected_tabs'] = []
            else:
                # 保留用户选择，但过滤掉已失效的标签页
                entry['selected_tabs'] = [t for t in saved_tabs if t in available_tabs]

        entry['sections'] = _normalise_sections(entry.get('sections'))
        entry['flatten'] = bool(entry.get('flatten', DEFAULT_FLATTEN))
        entry['skip'] = bool(entry.get('skip', False))
        entry['alias'] = str(entry.get('alias') or "").strip()

        normalised[course_id] = entry

    if normalised != data or created:
        payload = {
            'courses': normalised,
            '_note': "Edit per-course preferences. sections accepts a list of course menu names; include '*' to download all sections.",
        }
        try:
            with config_path.open('w', encoding='utf-8') as fp:
                json.dump(payload, fp, indent=2, ensure_ascii=False, sort_keys=True)
        except OSError as e:
            logger.error(f"Failed to write course config: {e}")
    
    return created, normalised
