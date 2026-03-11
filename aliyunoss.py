import sys
import os
import io
import json
import uuid
import random
import string
import requests
import hashlib
import urllib3
import threading
from datetime import datetime
from queue import Queue

from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox, QSizeGrip
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QObject, QEvent
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===================== 全局配置 & 核心逻辑 =====================
BUCKETS_FILE = 'aliyun.txt'
HISTORY_FILE = "upload_history.json"
THREAD_NUM = 3
file_queue = Queue()

REGION_MAP = {
    'Beijing': 'oss-cn-beijing', 
    'Tianjin': 'oss-cn-beijing', 
    'Hebei': 'oss-cn-zhangjiakou', 
    'Shanxi': 'oss-cn-beijing', 
    'Nei Mongol': 'oss-cn-huhehaote', 
    'Inner Mongolia': 'oss-cn-huhehaote',
    'Liaoning': 'oss-cn-beijing', 
    'Jilin': 'oss-cn-beijing', 
    'Heilongjiang': 'oss-cn-beijing',
    'Shanghai': 'oss-cn-shanghai', 
    'Jiangsu': 'oss-cn-shanghai', 
    'Zhejiang': 'oss-cn-hangzhou', 
    'Anhui': 'oss-cn-shanghai', 
    'Fujian': 'oss-cn-hangzhou', 
    'Jiangxi': 'oss-cn-hangzhou', 
    'Shandong': 'oss-cn-qingdao',
    'Henan': 'oss-cn-beijing', 
    'Hubei': 'oss-cn-hangzhou', 
    'Hunan': 'oss-cn-guangzhou', 
    'Guangdong': 'oss-cn-shenzhen', 
    'Guangxi': 'oss-cn-guangzhou', 
    'Hainan': 'oss-cn-guangzhou',
    'Chongqing': 'oss-cn-chongqing', 
    'Sichuan': 'oss-cn-chengdu', 
    'Guizhou': 'oss-cn-chongqing', 
    'Yunnan': 'oss-cn-chengdu', 
    'Tibet': 'oss-cn-chengdu', 
    'Xizang': 'oss-cn-chengdu',
    'Shaanxi': 'oss-cn-beijing', 
    'Gansu': 'oss-cn-beijing', 
    'Qinghai': 'oss-cn-chengdu', 
    'Ningxia': 'oss-cn-beijing', 
    'Xinjiang': 'oss-cn-zhangjiakou', 
    'Hong Kong': 'oss-cn-hongkong', 
    'Macau': 'oss-cn-hongkong', 
    'Macao': 'oss-cn-hongkong', 
    'Taiwan': 'oss-cn-hongkong',
    'Singapore': 'oss-ap-southeast-1',      
    'Malaysia': 'oss-ap-southeast-3',        
    'Indonesia': 'oss-ap-southeast-5',      
    'Philippines': 'oss-ap-southeast-6',    
    'Thailand': 'oss-ap-southeast-7',        
    'Vietnam': 'oss-ap-southeast-1',        
    'Japan': 'oss-ap-northeast-1',          
    'South Korea': 'oss-ap-northeast-2',    
    'India': 'oss-ap-south-1',              
    'United Arab Emirates': 'oss-me-east-1',
    'Saudi Arabia': 'oss-me-central-1',     
    'United States': 'oss-us-west-1',        
    'Canada': 'oss-us-west-1',              
    'Australia': 'oss-ap-southeast-2',      
    'Germany': 'oss-eu-central-1',          
    'United Kingdom': 'oss-eu-west-1',      
    'France': 'oss-eu-central-1',
    'DEFAULT': 'oss-cn-hangzhou'
}

def load_buckets_by_region():
    pool = {}
    if os.path.exists(BUCKETS_FILE):
        with open(BUCKETS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip().rstrip('/')
                if not url: continue
                import re
                match = re.search(r'\.(oss-[a-z0-9-]+)\.aliyuncs\.com', url)
                if match:
                    r = match.group(1)
                    if r not in pool: pool[r] = []
                    pool[r].append(url)
    return pool

def load_and_migrate_history():
    default_data = {"folders": ["默认目录", "机密文件", "工作文档", "媒体资源"], "files": []}
    if not os.path.exists(HISTORY_FILE): return default_data
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
        if isinstance(data, list):
            for item in data:
                if 'id' not in item: item['id'] = uuid.uuid4().hex
                if 'folder' not in item: item['folder'] = "默认目录"
            data = {"folders": default_data["folders"], "files": data}
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
        return data
    except: return default_data

def save_history_data(data):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_strong_password(length=16):
    return ''.join(random.choice(string.ascii_letters + string.digits + "@#%^&*") for _ in range(length))

def generate_random_headers():
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15'
    ]
    return {
        'User-Agent': random.choice(user_agents),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': random.choice(['zh-CN,zh;q=0.9,en;q=0.8', 'en-US,en;q=0.9,zh-CN;q=0.8']),
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive'
    }

def strip_metadata(data: bytes, filename: str) -> bytes:
    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            data_only = list(img.getdata())
            clean_img = Image.new(img.mode, img.size)
            clean_img.putdata(data_only)
            out = io.BytesIO()
            fmt = img.format if img.format else ('JPEG' if ext in ['.jpg','.jpeg'] else 'PNG')
            clean_img.save(out, format=fmt)
            return out.getvalue()
        except Exception as e:
            print(f"元数据擦除失败，使用原数据: {e}")
            return data
    return data

def encrypt_data(file_data: bytes, password: str) -> bytes:
    key = hashlib.sha256(password.encode('utf-8')).digest()
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return iv + cipher.encrypt(pad(file_data, AES.block_size))

def decrypt_data(file_data: bytes, password: str) -> bytes:
    key = hashlib.sha256(password.encode('utf-8')).digest()
    iv = file_data[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(file_data[16:]), AES.block_size)


# ===================== 主界面 HTML =====================
MAIN_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>全局加密云盘</title>
    <style>
        :root {
            --glass-bg: rgba(255, 255, 255, 0.05);
            --glass-border: 1px solid rgba(255, 255, 255, 0.12);
            --glass-shadow: 0 15px 35px rgba(0, 0, 0, 0.6);
            --text-main: #ffffff;
            --text-sub: rgba(255, 255, 255, 0.65);
            --accent: #00f2fe;
            --accent-grad: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        body { margin: 0; font-family: 'Segoe UI', system-ui; background: transparent; color: var(--text-main); height: 100vh; overflow: hidden; display: flex; justify-content: center; align-items: center; user-select: none; }
        
        .app-container { width: 96%; height: 94%; background: rgba(18, 15, 45, 0.92); backdrop-filter: blur(35px); border-radius: 20px; border: var(--glass-border); box-shadow: var(--glass-shadow); display: flex; flex-direction: row; overflow: hidden; }
        
        /* 修改: 增加了 flex-shrink: 0 彻底防止侧边栏被挤压变形 */
        aside { width: 330px; flex-shrink: 0; background: rgba(255,255,255,0.02); border-right: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; padding: 25px; box-sizing: border-box; z-index: 10; cursor: move; }
        .brand-header { display: flex; align-items: center; margin-bottom: 30px; }
        .btn-close { background: #ff5f56 !important; width: 16px; height: 16px; border-radius: 50%; padding: 0 !important; border: none !important; margin-right: 15px; cursor: pointer; -webkit-app-region: no-drag;}
        h1 { margin: 0; font-size: 22px; font-weight: 500; letter-spacing: 1px; }
        h1 span { font-weight: 800; background: var(--accent-grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        .controls { display: flex; flex-direction: column; gap: 12px; margin-bottom: 25px; -webkit-app-region: no-drag;}
        .controls button { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 12px; border-radius: 12px; cursor: pointer; font-size: 14px; transition: 0.3s; width: 100%; text-align: center; }
        .controls button:hover { background: rgba(255,255,255,0.18); transform: translateY(-2px); }
        .controls button.primary { background: var(--accent-grad); border: none; color: #000; font-weight: 700; box-shadow: 0 6px 20px rgba(0, 242, 254, 0.35); }
        
        .config-panel { flex: 1; display: flex; flex-direction: column; gap: 16px; background: rgba(0,0,0,0.25); padding: 20px; border-radius: 16px; font-size: 14px; overflow-y: auto; -webkit-app-region: no-drag;}
        .config-panel::-webkit-scrollbar { width: 4px; }
        .config-row { display: flex; flex-direction: column; gap: 8px; }
        .config-row select, .config-row input { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 10px 12px; border-radius: 8px; outline: none; font-family: Consolas, monospace; font-size: 13px; width: 100%; box-sizing: border-box;}
        .config-row select option { background: #1a1a2e; color: white; padding: 10px;}
        .lbl-loc { color: var(--accent); font-weight: 600; font-size: 14px; word-break: break-all; display:flex; align-items:center; gap:6px;}
        .check-lbl { display:flex; align-items:flex-start; gap:8px; color:#fff; font-size:13px; cursor:pointer; line-height: 1.4;}
        .check-lbl input { width:16px; height:16px; cursor:pointer; accent-color: var(--accent); margin-top: 2px;}

        /* 修改: 增加了 min-width: 0 保证超出内容被截断而不是撑爆布局 */
        main { flex: 1; min-width: 0; display: flex; flex-direction: column; background: rgba(0,0,0,0.1); cursor: move;}
        .main-header { padding: 25px 35px; border-bottom: 1px solid rgba(255,255,255,0.06); font-weight: bold; font-size: 16px; color: var(--text-sub); }
        
        .file-list { flex: 1; padding: 25px 35px; overflow-y: auto; -webkit-app-region: no-drag;}
        .file-list::-webkit-scrollbar { width: 8px; }
        .file-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 10px; }
        .empty-tip { text-align: center; margin-top: 150px; color: var(--text-sub); font-size: 16px; opacity: 0.7; font-weight: 300; }
        
        .card { background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 18px; padding: 22px; margin-bottom: 20px; transition: 0.3s; }
        .card:hover { background: rgba(255, 255, 255, 0.05); }
        .card-header { display: flex; align-items: center; margin-bottom: 15px; }
        .icon { width: 48px; height: 48px; border-radius: 14px; background: rgba(255,255,255,0.08); display: flex; align-items: center; justify-content: center; margin-right: 20px; font-size: 24px; }
        /* 修改: 增加了 min-width: 0 保证文字省略号正常工作 */
        .info { flex: 1; overflow: hidden; min-width: 0; }
        .filename { font-size: 16px; font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .status { font-size: 14px; color: var(--text-sub); margin-top: 8px; }
        .progress-track { height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; margin-top: 15px; }
        .progress-bar { height: 100%; width: 0%; background: var(--accent-grad); transition: width 0.3s ease-out; }
        
        .result-panel { margin-top: 18px; background: rgba(0,0,0,0.4); border-radius: 12px; padding: 18px; display: none; border: 1px solid rgba(255,255,255,0.05); }
        .link-row { display: flex; align-items: center; margin-bottom: 12px; }
        .link-row:last-child { margin-bottom: 0; }
        .label { width: 55px; color: var(--text-sub); font-size: 13px; flex-shrink: 0; }
        .value-box { flex: 1; background: rgba(255,255,255,0.06); padding: 10px 15px; border-radius: 8px; color: var(--accent); cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: 0.2s; font-family: 'Consolas', monospace; font-size: 13px; }
        .value-box:hover { background: rgba(255,255,255,0.15); color: #fff; }

        .toast { position: fixed; bottom: 40px; left: 50%; transform: translateX(-50%); background: #fff; color: #000; padding: 12px 35px; border-radius: 50px; font-size: 15px; font-weight: bold; opacity: 0; transition: 0.4s; pointer-events: none; z-index: 999; box-shadow: 0 8px 25px rgba(0,0,0,0.3);}
        .toast.show { opacity: 1; transform: translate(-50%, -10px); }
    </style>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
    <div class="app-container">
        <aside>
            <div class="brand-header">
                <button class="btn-close" onclick="backend.close_app()"></button>
                <h1><span>Crypto</span> OSS Box</h1>
            </div>
            
            <div class="controls">
                <button onclick="backend.open_history_window()">📁 资源管理器</button>
                <button onclick="backend.select_files_trigger()">➕ 添加文件</button>
                <button class="primary" onclick="startUpload()">🚀 开始加密上传</button>
            </div>
            
            <div class="config-panel">
                <div class="config-row">
                    <span style="color:var(--text-sub);">📍 定位:</span>
                    <span id="locDisplay" class="lbl-loc">正在获取防追踪智能路由...</span>
                </div>
                <div class="config-row">
                    <span style="color:var(--text-sub);">🌐 节点:</span>
                    <select id="regionSelect" onchange="regionChanged()"><option>等待初始化...</option></select>
                    <select id="nodeSelect"></select>
                </div>
                <div class="config-row">
                    <span style="color:var(--text-sub);">🔑 密钥:</span>
                    <input type="text" id="aesPwd" placeholder="清空则不加密">
                    <button style="background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.2); color:white; padding:8px; border-radius:8px; cursor:pointer; font-size:12px; margin-top:5px;" onclick="backend.req_new_pwd()">随机生成</button>
                </div>
                <div class="config-row">
                    <span style="color:var(--text-sub);">🛡️ 隐私:</span>
                    <label class="check-lbl">
                        <input type="checkbox" id="stripMeta" checked>
                        强力抹除文件元数据<br>(彻底剥离EXIF、GPS等隐私)
                    </label>
                </div>
            </div>
        </aside>

        <main>
            <div class="main-header">上传任务队列</div>
            <div class="file-list" id="fileList"><div class="empty-tip">点击左侧“添加文件”以开始</div></div>
        </main>
    </div>
    <div id="toast" class="toast">已复制到剪贴板</div>

    <script>
        let backend;
        new QWebChannel(qt.webChannelTransport, function(channel) {
            backend = channel.objects.backend;
            backend.sig_files_added.connect(renderFiles);
            backend.sig_progress.connect(updateProgress);
            backend.sig_status.connect(updateStatusText);
            backend.sig_upload_done.connect(showResult);
            backend.sig_toast.connect(showToast);
            
            backend.sig_init_ui.connect(function(regionsStr, pwd) {
                document.getElementById('aesPwd').value = pwd;
                let rSel = document.getElementById('regionSelect');
                rSel.innerHTML = '<option value="auto">自动分配 (IP定位)</option>';
                JSON.parse(regionsStr).forEach(item => rSel.innerHTML += `<option value="${item.id}">${item.id}</option>`);
            });
            backend.sig_update_nodes.connect(function(nodesStr) {
                let nSel = document.getElementById('nodeSelect');
                nSel.innerHTML = '';
                let nodes = JSON.parse(nodesStr);
                if(nodes.length === 0) nSel.innerHTML = '<option value="">❌ 该区域无可用节点</option>';
                else nodes.forEach(n => nSel.innerHTML += `<option value="${n.url}">${n.url}</option>`);
            });
            backend.sig_update_loc.connect(locHtml => document.getElementById('locDisplay').innerHTML = locHtml);
            backend.sig_new_pwd.connect(pwd => document.getElementById('aesPwd').value = pwd);
            
            backend.ui_ready();
        });

        function regionChanged() { backend.change_region(document.getElementById('regionSelect').value); }
        function startUpload() {
            let node = document.getElementById('nodeSelect').value;
            let pwd = document.getElementById('aesPwd').value;
            let strip = document.getElementById('stripMeta').checked;
            backend.start_upload_trigger(node, pwd, strip);
        }

        function renderFiles(filesJson) {
            const files = JSON.parse(filesJson);
            const container = document.getElementById('fileList');
            container.innerHTML = '';
            files.forEach(f => {
                const div = document.createElement('div');
                div.className = 'card'; div.id = 'file-' + CSS.escape(f.name);
                div.innerHTML = `
                    <div class="card-header"><div class="icon">📄</div>
                        <div class="info"><div class="filename">${f.name}</div><div class="status">准备就绪</div></div>
                    </div>
                    <div class="progress-track"><div class="progress-bar"></div></div>
                    <div class="result-panel"></div>`;
                container.appendChild(div);
            });
        }

        function updateProgress(name, percent) {
            const el = document.getElementById('file-' + CSS.escape(name));
            if (el) { el.querySelector('.progress-bar').style.width = percent + '%'; el.querySelector('.status').innerText = `正在处理 ${percent}%`; }
        }

        function updateStatusText(name, text, color) {
            const el = document.getElementById('file-' + CSS.escape(name));
            if (el) { const statusEl = el.querySelector('.status'); statusEl.innerText = text; if(color) statusEl.style.color = color; }
        }

        function showResult(resultJson) {
            const res = JSON.parse(resultJson);
            const el = document.getElementById('file-' + CSS.escape(res.name));
            if (!el) return;
            const statusEl = el.querySelector('.status'); const barEl = el.querySelector('.progress-bar'); const panel = el.querySelector('.result-panel');

            if (res.success) {
                statusEl.innerHTML = '<span style="color:#00c853">上传成功</span>';
                barEl.style.background = '#00c853'; barEl.style.width = '100%';
                let html = `<div class="link-row"><span class="label">链接</span><div class="value-box" title="点击获取链接" onclick="copyText('${res.url}', '链接已复制')">${res.url}</div></div>`;
                if(res.is_enc) {
                    html += `<div class="link-row"><span class="label">密钥</span><div class="value-box" style="color:#ffb300;" title="点击获取密钥" onclick="copyText('${res.pwd}', '密钥已复制')">${res.pwd}</div></div>`;
                }
                panel.innerHTML = html; panel.style.display = 'block';
            } else {
                statusEl.innerHTML = `<span style="color:#ff3d00">失败: ${res.msg}</span>`; barEl.style.background = '#ff3d00';
            }
        }

        function copyText(text, msg) { if(backend) { backend.copy_to_clipboard(text); showToast(msg); } }
        function showToast(msg) {
            const t = document.getElementById('toast'); t.innerText = msg || "已复制";
            t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 2000);
        }
    </script>
</body>
</html>
"""

# ===================== 历史记录界面 HTML =====================
HISTORY_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>云端资源管理器</title>
    <style>
        :root { --text-main: #ffffff; --text-sub: rgba(255,255,255,0.65); --accent: #00f2fe; --bg-panel: rgba(0,0,0,0.3); }
        body { margin: 0; font-family: 'Segoe UI', system-ui; background: rgba(18, 15, 45, 0.96); color: var(--text-main); height: 100vh; display: flex; flex-direction: column; user-select: none; }
        header { padding: 20px 30px; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; cursor: move; -webkit-app-region: drag; background: rgba(255,255,255,0.02);}
        .title { font-size: 18px; font-weight: bold; display: flex; align-items: center; gap: 12px;}
        .btn-close { background: #ff5f56; width: 16px; height: 16px; border-radius: 50%; border: none; cursor: pointer; -webkit-app-region: no-drag; }
        
        .explorer { display: flex; flex: 1; overflow: hidden; }
        
        /* 修改: flex-shrink: 0 防止侧边栏变形 */
        .sidebar { width: 240px; flex-shrink: 0; background: rgba(255,255,255,0.02); border-right: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; -webkit-app-region: no-drag; }
        .sidebar-header { padding: 20px 15px 15px 15px; font-size: 13px; color: var(--text-sub); text-transform: uppercase; letter-spacing: 1px; display: flex; justify-content: space-between; align-items: center; font-weight: 600;}
        .btn-add-folder { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 18px; transition: 0.2s;}
        .btn-add-folder:hover { transform: scale(1.2); }
        
        .folder-list { flex: 1; overflow-y: auto; padding: 0 12px; }
        .folder-item { padding: 12px 18px; border-radius: 10px; margin-bottom: 8px; cursor: pointer; display: flex; align-items: center; gap: 12px; color: var(--text-sub); font-size: 15px; transition: 0.2s; border: 1px solid transparent; }
        .folder-item:hover { background: rgba(255,255,255,0.06); color: #fff; }
        .folder-item.active { background: rgba(0, 242, 254, 0.15); color: #fff; border-color: rgba(0, 242, 254, 0.3); font-weight: bold;}
        .folder-item.drag-over { background: rgba(255, 179, 0, 0.25); border-color: #ffb300; }
        
        /* 修改: min-width: 0 截断超长内容 */
        .main-content { flex: 1; min-width: 0; display: flex; flex-direction: column; background: rgba(0,0,0,0.15); -webkit-app-region: no-drag;}
        .toolbar { padding: 18px 30px; border-bottom: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; gap: 18px; font-size: 15px; }
        
        .file-list { flex: 1; overflow-y: auto; padding: 25px 30px; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); align-content: start; gap: 20px; }
        .file-list::-webkit-scrollbar, .folder-list::-webkit-scrollbar { width: 6px; }
        .file-list::-webkit-scrollbar-thumb, .folder-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 10px; }
        
        .file-card { background: var(--bg-panel); border-radius: 14px; padding: 18px; border: 1px solid rgba(255,255,255,0.06); position: relative; cursor: grab; transition: 0.2s; min-width: 0;}
        .file-card:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.4); border-color: rgba(255,255,255,0.15); }
        .file-card:active { cursor: grabbing; }
        
        .file-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px; }
        .file-name { font-weight: bold; font-size: 14px; word-break: break-all; padding-right: 65px; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;}
        .badge { position: absolute; top: 18px; right: 18px; font-size: 11px; padding: 4px 8px; border-radius: 6px; font-weight: bold;}
        .badge.enc { background: rgba(255, 179, 0, 0.18); color: #ffb300; border: 1px solid rgba(255, 179, 0, 0.35); }
        .badge.plain { background: rgba(0, 200, 83, 0.18); color: #00c853; border: 1px solid rgba(0, 200, 83, 0.35); }
        
        .data-row { background: rgba(0,0,0,0.4); padding: 10px 12px; border-radius: 8px; font-family: Consolas; font-size: 12px; color: var(--accent); margin-bottom: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; border: 1px solid transparent; transition: 0.2s;}
        .data-row:hover { border-color: var(--accent); color: #fff; }
        .data-row.key { color: #ffb300; }
        .data-row.key:hover { border-color: #ffb300; }
        
        .btn-group { display: flex; gap: 10px; margin-top: 12px; }
        .btn-action { flex: 1; background: rgba(255,255,255,0.1); color: white; border: none; padding: 10px; border-radius: 8px; font-size: 13px; cursor: pointer; transition: 0.3s; }
        .btn-action.dl:hover { background: var(--accent-grad); color: #000; font-weight: bold; box-shadow: 0 4px 15px rgba(0, 242, 254, 0.3); }
        .btn-action.del { background: rgba(255, 95, 86, 0.1); color: #ff5f56; }
        .btn-action.del:hover { background: #ff5f56; color: #fff; box-shadow: 0 4px 15px rgba(255, 95, 86, 0.3); }

        .toast { position: fixed; bottom: 40px; left: 50%; transform: translateX(-50%); background: #fff; color: #000; padding: 12px 35px; border-radius: 50px; font-size: 14px; font-weight: bold; opacity: 0; transition: 0.4s; pointer-events: none; z-index: 999; box-shadow: 0 5px 20px rgba(0,0,0,0.4);}
        .toast.show { opacity: 1; transform: translate(-50%, -10px); }
        .empty { grid-column: 1 / -1; text-align: center; margin-top: 150px; color: var(--text-sub); font-size: 16px;}
    </style>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
    <header>
        <div class="title">📁 云端资源管理器</div>
        <button class="btn-close" onclick="hb.close_window()"></button>
    </header>
    
    <div class="explorer">
        <div class="sidebar">
            <div class="sidebar-header">
                <span>我的文件夹</span>
                <button class="btn-add-folder" onclick="addFolder()" title="新建文件夹">➕</button>
            </div>
            <div class="folder-list" id="folderList"></div>
        </div>
        
        <div class="main-content">
            <div class="toolbar">
                <span style="color:var(--text-sub);">当前路径:</span>
                <span id="currentPath" style="font-weight:bold; color:#fff;">默认目录</span>
                <span style="flex:1;"></span>
                <span style="font-size:13px; color:var(--text-sub);">💡 提示：按住文件拖拽即可分类</span>
            </div>
            <div class="file-list" id="fileList"></div>
        </div>
    </div>
    
    <div id="toast" class="toast">操作成功</div>

    <script>
        let db = { folders: [], files: [] };
        let currentFolder = "默认目录";
        let hb;

        new QWebChannel(qt.webChannelTransport, function(channel) {
            hb = channel.objects.history_backend;
            hb.sig_load_data.connect(function(dataStr) {
                db = JSON.parse(dataStr);
                if(!db.folders.includes(currentFolder) && db.folders.length > 0) currentFolder = db.folders[0];
                renderFolders();
                renderFiles();
            });
            hb.sig_toast.connect(showToast);
            hb.request_data();
        });

        function selectFolder(fname) {
            currentFolder = fname;
            document.getElementById('currentPath').innerText = fname;
            renderFolders();
            renderFiles();
        }

        function addFolder() {
            let name = prompt("请输入新文件夹名称:");
            if(name && name.trim() !== "") {
                if(db.folders.includes(name.trim())) { showToast("文件夹已存在"); return; }
                hb.add_folder(name.trim());
            }
        }

        function renderFolders() {
            const container = document.getElementById('folderList');
            let html = '';
            db.folders.forEach(f => {
                let active = f === currentFolder ? 'active' : '';
                html += `<div class="folder-item ${active}" onclick="selectFolder('${f}')" 
                              ondrop="drop(event, '${f}')" ondragover="allowDrop(event)" ondragleave="leaveDrop(event)">
                            📁 ${f}
                         </div>`;
            });
            container.innerHTML = html;
        }

        function renderFiles() {
            const container = document.getElementById('fileList');
            let filtered = db.files.filter(i => i.folder === currentFolder);
            if (filtered.length === 0) { container.innerHTML = `<div class="empty">此文件夹为空</div>`; return; }

            let html = '';
            filtered.forEach(item => {
                let badge = item.is_enc ? '<span class="badge enc">🔒 加密</span>' : '<span class="badge plain">明文</span>';
                html += `<div class="file-card" draggable="true" ondragstart="drag(event, '${item.id}')">
                            <div class="file-header">
                                <div class="file-name" title="${item.filename}">${item.filename}</div>
                                ${badge}
                            </div>
                            <div class="data-row" title="点击复制链接" onclick="copyText('${item.url}', '链接已复制')">${item.url}</div>`;
                if(item.is_enc && item.password) {
                    html += `<div class="data-row key" title="点击复制密钥" onclick="copyText('${item.password}', '密钥已复制')">🔑 ${item.password}</div>`;
                }
                
                html += `<div class="btn-group">
                            <button class="btn-action dl" onclick="dl('${item.id}')">📥 提取下载</button>
                            <button class="btn-action del" onclick="delFile('${item.id}', '${item.filename}')">🗑️ 删除记录</button>
                         </div>
                         </div>`;
            });
            container.innerHTML = html;
        }

        function drag(ev, id) {
            ev.dataTransfer.setData("text/plain", id);
            ev.dataTransfer.effectAllowed = "move";
        }
        function allowDrop(ev) {
            ev.preventDefault();
            ev.currentTarget.classList.add('drag-over');
        }
        function leaveDrop(ev) {
            ev.currentTarget.classList.remove('drag-over');
        }
        function drop(ev, targetFolder) {
            ev.preventDefault();
            ev.currentTarget.classList.remove('drag-over');
            let fileId = ev.dataTransfer.getData("text/plain");
            if(targetFolder !== currentFolder) {
                hb.move_file(fileId, targetFolder);
            }
        }

        function dl(fileId) {
            let item = db.files.find(i => i.id === fileId);
            if(item) hb.trigger_download(item.url, item.filename, item.is_enc, item.password || "");
        }

        function delFile(fileId, filename) {
            if (confirm(`确定要从本地历史记录中删除 "${filename}" 吗？\\n(注意：这并不会删除云端的真实文件)`)) {
                hb.delete_file(fileId);
            }
        }

        function copyText(text, msg) { if(hb) { hb.copy_to_clipboard(text); showToast(msg); } }
        function showToast(msg) {
            const t = document.getElementById('toast'); t.innerText = msg;
            t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 2000);
        }
    </script>
</body>
</html>
"""

# ===================== 后端逻辑 =====================
class HistoryBackend(QObject):
    sig_load_data = pyqtSignal(str)
    sig_toast = pyqtSignal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window

    @pyqtSlot()
    def close_window(self): self.window.close()

    @pyqtSlot(str)
    def copy_to_clipboard(self, text): QApplication.clipboard().setText(text)

    @pyqtSlot()
    def request_data(self):
        data = load_and_migrate_history()
        self.sig_load_data.emit(json.dumps(data))

    @pyqtSlot(str)
    def add_folder(self, folder_name):
        data = load_and_migrate_history()
        if folder_name not in data["folders"]:
            data["folders"].append(folder_name)
            save_history_data(data)
            self.sig_toast.emit(f"已创建文件夹: {folder_name}")
            self.request_data()

    @pyqtSlot(str, str)
    def move_file(self, file_id, target_folder):
        data = load_and_migrate_history()
        moved = False
        for f in data["files"]:
            if f.get("id") == file_id:
                f["folder"] = target_folder
                moved = True
                break
        if moved:
            save_history_data(data)
            self.sig_toast.emit("✅ 移动成功")
            self.request_data()

    @pyqtSlot(str)
    def delete_file(self, file_id):
        data = load_and_migrate_history()
        original_length = len(data["files"])
        data["files"] = [f for f in data["files"] if f.get("id") != file_id]
        
        if len(data["files"]) < original_length:
            save_history_data(data)
            self.sig_toast.emit("✅ 已从本地删除该记录")
            self.request_data() 
        else:
            self.sig_toast.emit("❌ 未找到该文件记录")

    @pyqtSlot(str, str, bool, str)
    def trigger_download(self, url, filename, is_enc, pwd):
        save_path, _ = QFileDialog.getSaveFileName(None, "保存文件", filename.replace('.enc', '') if is_enc else filename)
        if not save_path: return
        self.sig_toast.emit("开始下载，请稍候...")
        threading.Thread(target=self.dl_worker, args=(url, save_path, is_enc, pwd), daemon=True).start()

    def dl_worker(self, url, save_path, is_enc, pwd):
        try:
            resp = requests.get(url, headers=generate_random_headers(), timeout=60)
            if resp.ok:
                data = resp.content
                if is_enc and pwd: data = decrypt_data(data, pwd)
                with open(save_path, 'wb') as f: f.write(data)
                self.sig_toast.emit("✅ 下载且解密成功！")
            else:
                self.sig_toast.emit(f"❌ 下载失败 HTTP {resp.status_code}")
        except Exception as e:
            self.sig_toast.emit(f"❌ 错误: {str(e)}")

class Backend(QObject):
    sig_init_ui = pyqtSignal(str, str)
    sig_update_nodes = pyqtSignal(str)
    sig_update_loc = pyqtSignal(str)
    sig_new_pwd = pyqtSignal(str)
    
    sig_files_added = pyqtSignal(str)
    sig_progress = pyqtSignal(str, int)
    sig_status = pyqtSignal(str, str, str)
    sig_upload_done = pyqtSignal(str)
    sig_toast = pyqtSignal(str)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.pool = load_buckets_by_region()
        self.upload_files = []
        self.auto_region = "oss-cn-hangzhou"

    @pyqtSlot()
    def ui_ready(self):
        regions_data = [{"id": r_id} for r_id in self.pool.keys()]
        pwd = generate_strong_password()
        self.sig_init_ui.emit(json.dumps(regions_data), pwd)
        threading.Thread(target=self.locate_ip, daemon=True).start()

    def locate_ip(self):
        url = 'https://api.db-ip.com/v2/free/self'
        try:
            print(f"正在直接请求接口: {url}")
            resp_raw = requests.get(url, timeout=5)
            print(f"返回状态码: {resp_raw.status_code}")
            
            if resp_raw.status_code == 200:
                resp = resp_raw.json()
                print("原始返回结果:", json.dumps(resp, ensure_ascii=False))
                
                code = resp.get('country_code', 'cn').lower()
                
                if code == 'cn':
                    loc = resp.get('region') or resp.get('stateProv') or 'China'
                else:
                    loc = resp.get('countryName') or 'Unknown'
                
                r_id = REGION_MAP.get(loc)
                
                if not r_id:
                    continent = resp.get('continent_code', '')
                    if continent == 'EU': r_id = 'oss-eu-central-1'      
                    elif continent == 'AS': r_id = 'oss-ap-southeast-1'  
                    elif continent == 'NA': r_id = 'oss-us-west-1'       
                    elif continent == 'SA': r_id = 'oss-us-west-1'       
                    elif continent == 'OC': r_id = 'oss-ap-southeast-2'  
                    elif continent == 'AF': r_id = 'oss-eu-central-1'    
                    else: r_id = REGION_MAP['DEFAULT']
                
                self.auto_region = r_id
                
                flag_url = f"https://assets.ipstack.com/flags/{code}.svg"
                loc_html = f"<img src='{flag_url}' width='20' style='vertical-align:middle;'> <b>{loc}</b>"
                
                self.sig_update_loc.emit(loc_html)
                self.change_region('auto')
            else:
                error_msg = f"请求失败 {resp_raw.status_code}: {resp_raw.text[:50]}"
                print(error_msg)
                self.sig_update_loc.emit(f"<span style='color:red;'>{error_msg}</span>")
                self.change_region('auto')

        except Exception as e:
            print(f"请求发生异常: {e}")
            self.sig_update_loc.emit(f"请求异常: {str(e)[:30]}")
            self.change_region('auto')


    @pyqtSlot(str)
    def change_region(self, r_val):
        target = self.auto_region if r_val == 'auto' else r_val
        nodes = self.pool.get(target, [])
        nodes_data = [{"url": n} for n in nodes]
        self.sig_update_nodes.emit(json.dumps(nodes_data))

    @pyqtSlot()
    def req_new_pwd(self): self.sig_new_pwd.emit(generate_strong_password())

    @pyqtSlot()
    def open_history_window(self): self.main_window.show_history()

    @pyqtSlot(str)
    def copy_to_clipboard(self, text): QApplication.clipboard().setText(text)

    @pyqtSlot()
    def close_app(self): QApplication.quit()

    @pyqtSlot()
    def select_files_trigger(self):
        files, _ = QFileDialog.getOpenFileNames(None, "选择文件", "", "All Files (*.*)")
        if not files: return
        self.upload_files = list(files)
        preview = [{"name": os.path.basename(f)} for f in files]
        self.sig_files_added.emit(json.dumps(preview))

    @pyqtSlot(str, str, bool)
    def start_upload_trigger(self, node, pwd, strip_meta):
        if not self.upload_files: 
            self.sig_toast.emit("请先选择文件"); return
        if not node or "❌" in node:
            self.sig_toast.emit("请选择有效的上传节点"); return
            
        for f in self.upload_files: file_queue.put((f, node, pwd, strip_meta))
        for _ in range(min(THREAD_NUM, file_queue.qsize())):
            threading.Thread(target=self.upload_worker, daemon=True).start()
        self.upload_files = []

    def upload_worker(self):
        while not file_queue.empty():
            fpath, node, pwd, strip_meta = file_queue.get()
            fname = os.path.basename(fpath)
            try:
                self.sig_status.emit(fname, "读取与处理中...", "")
                with open(fpath, 'rb') as f: data = f.read()
                
                if strip_meta:
                    self.sig_status.emit(fname, "正在强力抹除隐私元数据...", "#ffb300")
                    data = strip_metadata(data, fname)

                is_enc = bool(pwd.strip())
                if is_enc:
                    self.sig_status.emit(fname, "执行 AES-256 加密...", "")
                    data = encrypt_data(data, pwd.strip())
                    fname += ".enc"

                url = f"{node}/{fname}"
                self.sig_status.emit(fname, "正在推送到云端...", "")
                
                resp = requests.put(url, data=data, headers=generate_random_headers(), timeout=60)
                
                if resp.status_code == 200:
                    res = {"name": os.path.basename(fpath), "success": True, "url": url, "is_enc": is_enc, "pwd": pwd}
                    self.save_history(res)
                else:
                    res = {"name": os.path.basename(fpath), "success": False, "msg": f"HTTP {resp.status_code}"}
                self.sig_upload_done.emit(json.dumps(res))
            except Exception as e:
                self.sig_upload_done.emit(json.dumps({"name": os.path.basename(fpath), "success": False, "msg": str(e)}))
            finally:
                file_queue.task_done()

    def save_history(self, res):
        data = load_and_migrate_history()
        data["files"].insert(0, {
            "id": uuid.uuid4().hex,
            "folder": "默认目录",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filename": res['name'],
            "url": res['url'],
            "is_enc": res['is_enc'],
            "password": res.get('pwd', '')
        })
        save_history_data(data)

# ===================== 窗口类 =====================
class HistoryWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize(1000, 680)  
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.view = QWebEngineView(self)
        self.view.page().setBackgroundColor(Qt.transparent)
        
        self.channel = QWebChannel()
        self.history_backend = HistoryBackend(self)
        self.channel.registerObject("history_backend", self.history_backend)
        self.view.page().setWebChannel(self.channel)
        
        self.view.setHtml(HISTORY_HTML)
        self.setCentralWidget(self.view)
        
        self.drag_pos = None
        if self.view.focusProxy(): self.view.focusProxy().installEventFilter(self)

        # 添加调整大小手柄
        self.grip = QSizeGrip(self)
        self.grip.resize(20, 20)

    # 监听窗口大小变化以移动手柄位置
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.grip.move(self.width() - 20, self.height() - 20)

    def eventFilter(self, source, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton and event.pos().y() < 60:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft(); return False
        elif event.type() == QEvent.MouseMove and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos); return True
        elif event.type() == QEvent.MouseButtonRelease: self.drag_pos = None
        return super().eventFilter(source, event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1000, 680) 
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.view = QWebEngineView()
        self.view.page().setBackgroundColor(Qt.transparent)
        
        self.channel = QWebChannel()
        self.backend = Backend(self)
        self.channel.registerObject("backend", self.backend)
        self.view.page().setWebChannel(self.channel)
        
        self.view.setHtml(MAIN_HTML)
        self.setCentralWidget(self.view)
        
        self.history_win = None
        self.drag_position = None
        if self.view.focusProxy(): self.view.focusProxy().installEventFilter(self)

        # 添加调整大小手柄
        self.grip = QSizeGrip(self)
        self.grip.resize(20, 20)

    # 监听窗口大小变化以移动手柄位置
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.grip.move(self.width() - 20, self.height() - 20)

    def show_history(self):
        if not self.history_win: self.history_win = HistoryWindow(self)
        self.history_win.show()
        self.history_win.raise_()
        self.history_win.activateWindow()
        self.history_win.history_backend.request_data()

    def eventFilter(self, source, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton and event.pos().y() < 80:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft(); return False
        elif event.type() == QEvent.MouseMove and self.drag_position:
            self.move(event.globalPos() - self.drag_position); return True
        elif event.type() == QEvent.MouseButtonRelease: self.drag_position = None
        return super().eventFilter(source, event)

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())