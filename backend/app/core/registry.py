from fastapi import FastAPI


def register_modules(app: FastAPI, modules) -> None:
    """按顺序注册模块；每个模块须暴露 register_module(app)（PRD §24.1）。

    本文件不允许 import 任何具体模块 —— 新增模块只改 modules/__init__.py。
    """
    for module in modules:
        module.register_module(app)
