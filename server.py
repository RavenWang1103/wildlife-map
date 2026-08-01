#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国野生动物分布地图 · 本地预览服务器

用法:
    python3 server.py            # 启动后自动打开浏览器
    python3 server.py --port 9000  # 指定端口
    python3 server.py --no-open  # 不自动打开浏览器

零依赖（仅用 Python 标准库），端口被占用时自动递增尝试。
"""
import argparse
import os
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial

# 以脚本所在目录为站点根目录，避免从其他目录运行时 404
ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 8080


class Handler(SimpleHTTPRequestHandler):
    """静态文件服务：默认从项目根目录提供，并支持常见的静态文件缓存头。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # 数据文件允许浏览器缓存，减少重复下载
        if self.path.startswith("/data/"):
            self.send_header("Cache-Control", "max-age=3600")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def pick_port(start):
    """从 start 开始找一个可用端口，找不到则报错退出。"""
    import socket
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    print("端口 %d-%d 均被占用，请换一个端口重试。" % (start, start + 19))
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="野生动物分布地图本地预览服务器")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="起始端口（默认 %d）" % DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    port = pick_port(args.port)
    url = "http://localhost:%d/" % port

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("=" * 52)
    print("  中国野生动物分布地图 · 本地预览")
    print("  访问地址: %s" % url)
    print("  站点目录: %s" % ROOT)
    print("  按 Ctrl+C 停止服务")
    print("=" * 52)

    if not args.no_open:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
        httpd.server_close()


if __name__ == "__main__":
    main()
