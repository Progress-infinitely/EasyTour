from __future__ import annotations

"""项目路径工具。

这个文件专门负责“告诉其他模块，关键目录在哪里”。
把路径集中管理，而不是散落在代码各处硬编码，有两个直接好处：
1. 目录结构调整时，只需要改少量地方。
2. 读代码时更容易看出“这个路径是干什么的”。
"""

from pathlib import Path


# `knowledge` 目录本身，是项目主体代码所在的位置。
KNOWLEDGE_ROOT = Path(__file__).resolve().parent.parent

# 运行时临时目录。
# 这里通常会放：上传文件、导入过程的中间产物、本地备份结果等。
LOCAL_BASE_DIR = KNOWLEDGE_ROOT / 'temp_data'

# 前端静态页面目录。
# FastAPI 会把这里的 HTML 直接作为页面入口暴露出去。
FRONT_PAGE_DIR = KNOWLEDGE_ROOT / 'front'


def get_local_base_dir() -> str:
    """返回临时文件目录，并确保目录存在。

    为什么函数里顺手 `mkdir`？
    因为第一次运行项目时，这个目录可能还不存在。
    在这里统一兜底后，其他代码就不需要反复判断“目录有没有先创建好”。
    """
    LOCAL_BASE_DIR.mkdir(parents=True, exist_ok=True)
    return str(LOCAL_BASE_DIR)


def get_front_page_dir() -> str:
    """返回前端静态页面目录，并确保目录存在。"""
    FRONT_PAGE_DIR.mkdir(parents=True, exist_ok=True)
    return str(FRONT_PAGE_DIR)
