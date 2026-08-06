#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国野生动物分布地图 · 本地预览服务器

用法:
    python3 server.py            # 启动后自动打开浏览器
    python3 server.py --port 9000  # 指定端口
    python3 server.py --no-open  # 不自动打开浏览器

零依赖（仅用 Python 标准库），端口被占用时自动递增尝试。
支持 gzip 压缩，大幅加速大 JSON 文件传输。
"""
import argparse
import gzip
import os
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

# 以脚本所在目录为站点根目录，避免从其他目录运行时 404
ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 8080

# 启用 gzip 的文件扩展名（仅压缩文本类，跳过图片）
GZIP_EXT = {'.html', '.htm', '.js', '.css', '.json', '.svg', '.txt', '.xml'}


class GzipHandler(SimpleHTTPRequestHandler):
    """支持 gzip 压缩的静态文件服务。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def send_head(self):
        path = self.translate_path(self.path)
        # 目录路径 → 查找 index.html
        if os.path.isdir(path):
            for idx in ('index.html', 'index.htm'):
                idx_path = os.path.join(path, idx)
                if os.path.isfile(idx_path):
                    path = idx_path
                    break
        if not os.path.isfile(path):
            return self.send_error(404, 'File not found')

        ctype = self.guess_type(path)
        ext = os.path.splitext(path)[1].lower()
        accept_gzip = self.headers.get('Accept-Encoding', '')
        mtime = self.date_time_string(os.path.getmtime(path))

        with open(path, 'rb') as f:
            raw = f.read()

        # 判断是否启用 gzip：文本类型 + 客户端支持 + 压缩后确实更小
        use_gzip = (ext in GZIP_EXT and 'gzip' in accept_gzip)
        if use_gzip:
            buf = BytesIO()
            with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6) as gz:
                gz.write(raw)
            compressed = buf.getvalue()
            if len(compressed) >= len(raw):
                use_gzip = False  # 压缩后反而更大，不启用

        self.send_response(200)
        self.send_header('Content-type', ctype)
        self.send_header('Last-Modified', mtime)
        if use_gzip:
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(compressed)))
            self.end_headers()
            return BytesIO(compressed)
        else:
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            return BytesIO(raw)

    def end_headers(self):
        # 数据文件允许浏览器缓存，减少重复下载
        if self.path.startswith('/data/'):
            self.send_header('Cache-Control', 'max-age=3600')
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stdout.write('[%s] %s\n' % (self.log_date_time_string(), fmt % args))


def pick_port(start):
    """从 start 开始找一个可用端口，找不到则报错退出。"""
    import socket
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    print('端口 %d-%d 均被占用，请换一个端口重试。' % (start, start + 19))
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='野生动物分布地图本地预览服务器')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                        help='起始端口（默认 %d）' % DEFAULT_PORT)
    parser.add_argument('--no-open', action='store_true',
                        help='不自动打开浏览器')
    args = parser.parse_args()

    port = pick_port(args.port)
    url = 'http://localhost:%d/' % port

    httpd = ThreadingHTTPServer(('127.0.0.1', port), GzipHandler)
    print('=' * 52)
    print('  中国野生动物分布地图 · 本地预览')
    print('  访问地址: %s' % url)
    print('  站点目录: %s' % ROOT)
    print('  按 Ctrl+C 停止服务')
    print('=' * 52)

    if not args.no_open:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止。')
        httpd.server_close()


if __name__ == '__main__':
    main()