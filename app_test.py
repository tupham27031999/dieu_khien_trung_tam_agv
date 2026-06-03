import os
import cv2
import json
from flask import Flask, render_template, url_for, jsonify, request, Response, send_from_directory
from config import AGVConfig
from config_2 import AGVConfig_2
import socket
import config
import requests
import shutil
from datetime import datetime
import numpy as np
import time
from urllib.parse import urlparse
import mo_phong_agv.tim_duong_di as tim_duong_di
import threading
from mo_phong_agv.fleet_logic_thuc_te import FleetLogicRealTime
from mo_phong_agv.simulation import AGVVisualizer
from mo_phong_agv.graph_manager import GraphManager
import cbs


def get_local_ip():
    """
    Tự động lấy địa chỉ IPv4 của máy tính trong mạng LAN.
    """
    s = None
    try:
        # Tạo một socket để kết nối ra ngoài.
        # Không cần gửi dữ liệu, chỉ cần thực hiện kết nối để hệ điều hành AGV_ENDPOINTS
        # chọn interface mạng phù hợp.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)) # 8.8.8.8 là DNS của Google
        ip_address = s.getsockname()[0]
        return ip_address
    except Exception as e:
        print(f"Không thể tự động lấy địa chỉ IP, sử dụng '127.0.0.1'. Lỗi: {e}")
        return "127.0.0.1" # Trả về localhost nếu có lỗi
    finally:
        if s:
            s.close()


PATH_DATA_IN_OUT = AGVConfig.PATH_PHAN_MEM + "/data_input_output"

# --- Cấu hình thời gian ---
AGV_UPDATE_INTERVAL = 1.0  # Thời gian nghỉ giữa các lần gửi dữ liệu (giây)

# --- Cấu hình API Điều khiển trung tâm (API Khác) ---
CHE_DO_API_TRUNG_TAM = False # Biến ON/OFF chế độ giao tiếp API khác
URL_API_TRUNG_TAM = "http://apbivnwb06:1332/api/AgvApi/update-status" # Thay đổi URL này thành API thực tế

CHE_DO_SENT_DATA_AGV = True # Biến ON/OFF chế độ gửi dữ liệu đến AGV


gui_dieu_khien_trung_tam = {
    "agv1": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv2": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv3": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv4": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv5": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv6": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
    "agv7": {"vi_tri_hien_tai": "", "trang_thai": "", "message": ""},
}

dieu_khien_trung_tam_gui = {
    "agv1": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv2": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv3": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv4": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv5": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv6": {"dich_den": "", "trang_thai": "", "message": ""},
    "agv7": {"dich_den": "", "trang_thai": "", "message": ""},
}

# Khởi tạo ứng dụng Flask
# template_folder: nơi chứa file html (templates)
# static_folder: nơi chứa css, js, images (static)
app = Flask(__name__)

# Nạp cấu hình (nếu cần dùng app.config['KEY'])
app.config.from_object(AGVConfig)



def update_agv_states():
    """
    Hàm cập nhật AGV_STATES dựa trên thông tin người dùng chọn (thong_tin_da_chon)
    và các biến điều khiển khác (dich_den_gui_agv).
    """
    # lấy thông tin đã chọn trên web
    for agv in AGVConfig.DANH_SACH_AGV:
        # Lấy thông tin cấu hình hiện tại của AGV
        user_config = AGVConfig.thong_tin_da_chon.get(agv, {})
        if (user_config.get("che_do_dieu_khien_truc_tiep") == "on") == True:
            # continue # Nếu chế độ điều khiển trực tiếp tắt, bỏ qua cập nhật trạng thái cho AGV này
            # 1. Cập nhật điểm cuối (đích đến)
            AGVConfig.AGV_STATES[agv]["dieu_khien_agv"]["diem_cuoi"] = AGVConfig.diem_cuoi_gui_agv.get(agv, "")
            
            # 2. Cập nhật trạng thái gửi AGV (logic: tra_hang/lay_hang -> giữ nguyên, khác -> nang)
            chon_gia = user_config.get("chon_gia_hang", "")
            if chon_gia == "lay_xe_linh_kien":
                AGVConfig.AGV_STATES[agv]["dieu_khien_agv"]["yeu_cau_gui_agv"] = "lay_xe_linh_kien"
            elif chon_gia == "tra_xe_linh_kien":
                AGVConfig.AGV_STATES[agv]["dieu_khien_agv"]["yeu_cau_gui_agv"] = "tra_xe_linh_kien"
            else:
                AGVConfig.AGV_STATES[agv]["dieu_khien_agv"]["yeu_cau_gui_agv"] = "lay_linh_kien"
            # 3. Cập nhật đường đi (Paths) - Tạm thời để rỗng
            # AGVConfig.AGV_STATES[agv]["paths"] = []
            # 4. Cập nhật các cờ Boolean (Chuyển đổi từ 'on'/'off' sang True/False)
            # AGVConfig.AGV_STATES[agv]["dieu_khien_agv"]["di_chuyen_khong_hang"] đã bị loại bỏ
            AGVConfig.che_do_dieu_khien_truc_tiep[agv] = (user_config.get("che_do_dieu_khien_truc_tiep") == "on")
        else:
            AGVConfig.che_do_dieu_khien_truc_tiep[agv] = False
            


    if CHE_DO_SENT_DATA_AGV:
        data_to_send_all = AGVConfig.AGV_STATES
        # print("data_to_send_all", data_to_send_all)
        # Gửi yêu cầu đến từng AGV
        for agv_id, endpoint in AGVConfig.AGV_ENDPOINTS.items():
            try:
                # if agv_id == "agv1":
                #     print(endpoint, " ppppppppppppppp")
                # Gửi dữ liệu của tất cả AGV cho mỗi AGV
                response = requests.post(endpoint, json=data_to_send_all, timeout=1)
                if response.status_code == 200:
                    response_data = response.json()
                    data_from_agv = response_data.get("data")
                    # Chỉ cập nhật nếu có 'data' và có key của agv_id tương ứng
                    # if data_from_agv and agv_id in data_from_agv:
                    #     received_state = data_from_agv[agv_id]
                    if data_from_agv:
                        # Cập nhật tất cả thông tin từ AGV
                        AGVConfig.AGV_STATES[agv_id]["thong_tin_agv"].update(data_from_agv)
                        
                        # Cập nhật thông tin IP kết nối và thời gian
                        parsed = urlparse(endpoint)
                        AGVConfig.danh_sach_ip_ket_noi[agv_id] = {
                            "address": parsed.netloc,
                            "last_seen": time.time()
                        }

                        print(f"--------Nhận phản hồi từ {agv_id}--------: {AGVConfig.AGV_STATES[agv_id]}")
                else:
                    print(f"Lỗi khi giao tiếp với {agv_id}: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Lỗi kết nối đến {agv_id} ({endpoint}): {e}")

    if CHE_DO_API_TRUNG_TAM:
        try:
            # 1. Chuẩn bị dữ liệu gửi đi (dạng gui_dieu_khien_trung_tam)
            payload_trung_tam = []
            for agv_id in AGVConfig.DANH_SACH_AGV:
                agv_num = int(agv_id.replace("agv", ""))
                if AGVConfig.che_do_dieu_khien_truc_tiep[agv_id] == False:
                    payload_trung_tam.append({
                        "AGV_ID": agv_num,
                        "Trang_thai": "",
                        "Vi_tri_hien_tai": AGVConfig.AGV_STATES[agv_id]["thong_tin_agv"]["diem_tiep_theo"],
                        "mgs": AGVConfig.AGV_STATES[agv_id]["thong_tin_agv"]["message"]
                    })
            # ví dụ
            payload_trung_tam = [{  "AGV_ID": 1,
                                    "Trang_thai": "PICKING",
                                    "Vi_tri_hien_tai": "A_02",
                                    "mgs": ""},
                                {   "AGV_ID": 2,
                                    "Trang_thai": "IDLE",
                                    "Vi_tri_hien_tai": "M00",
                                    "mgs": "test"}]
            # IDLE,       // Nghỉ / Chờ lệnh
            # PICKING,    // Đang lấy hàng
            # DROPPING,   // Đang trả hàng
            # CHARGING,   // Đang sạc
            # BLOCKED,    // Bị vật cản
            # ERROR,      // Lỗi kỹ thuật
            # OFFLINE     // Mất kết nối
            # 2. Gửi request
            response_tt = requests.post(URL_API_TRUNG_TAM, json=payload_trung_tam, timeout=1)
            # {'status': 'Success', 
            #  'commands': [{'agV_ID': 1, 'dich_den': 'B01', 'message': 'Moving to: B01', 'action': 'MOVE'}, 
            #               {'agV_ID': 2, 'dich_den': 'HOME', 'message': 'Moving to: HOME', 'action': 'MOVE'}]}
            # 3. Xử lý phản hồi (dạng dieu_khien_trung_tam_gui)
            if response_tt.status_code == 200:
                data_tt = response_tt.json()
                print(f"Nhận từ API trung tâm: {data_tt}")
                if "commands" in data_tt and isinstance(data_tt["commands"], list):
                    for cmd in data_tt["commands"]:
                        agv_id_num = cmd.get("agV_ID")
                        agv_key = f"agv{agv_id_num}"
                        diem_cuoi_moi = cmd.get("dich_den")

                        diem_cuoi_new = None
                        for _, point_data in AGVConfig.BAN_DO_KE.items():
                            for item in point_data:
                                # item cấu trúc ["TenKe", "TenDiem"]
                                if item[0] == diem_cuoi_moi:
                                    diem_cuoi_new = item[1]
                                    break
                            if diem_cuoi_new:
                                break
                        print("diem_cuoi_new", diem_cuoi_new)
                        if agv_key in AGVConfig.AGV_STATES:
                            # Cập nhật điểm cuối nếu có
                            if diem_cuoi_new:
                                AGVConfig.AGV_STATES[agv_key]["dieu_khien_agv"]["diem_cuoi"] = diem_cuoi_new
        except Exception as e:
            print(f"Lỗi kết nối API trung tâm: {e}")

@app.route('/')
def home():
    """
    Route trang chủ. Render home.html và truyền các tham số từ Config.
    """
    return render_template('home.html',
                           ten_dieu_de=AGVConfig.ten_dieu_de,
                           version=AGVConfig.VERSION,
                           danh_sach_agv=AGVConfig.DANH_SACH_AGV,
                           thong_tin_hien_thi=AGVConfig.thong_tin_hien_thi,
                           lua_chon_yeu_cau=AGVConfig.lua_chon_yeu_cau,
                           cac_gia_hang=AGVConfig.cac_gia_hang,
                           ban_do_ke=AGVConfig.BAN_DO_KE,
                           cac_loai_ke=AGVConfig.CAC_LOAI_KE,
                           thong_tin_da_chon=AGVConfig.thong_tin_da_chon,
                           gia_tri_hang_hien_tai=AGVConfig.gia_tri_hang_hien_tai,
                           agv_realtime_states=AGVConfig.AGV_STATES,
                           agv_colors=AGVConfig.agv_color,
                           map_resolution=AGVConfig.map_resolution,
                           kich_thuoc_agv=AGVConfig.kich_thuoc_agv,
                           hien_thi_diem=AGVConfig.hien_thi_diem,
                           hien_thi_duong=AGVConfig.hien_thi_duong)

@app.route('/api/get_info')
def get_info():
    """
    API trả về thông tin hiển thị mới nhất để JS cập nhật.
    """
    update_agv_states() # Cập nhật trạng thái mới nhất trước khi trả về (đảm bảo tính liên tục)
    return jsonify({
        'info': AGVConfig.thong_tin_hien_thi,
        'agv_states': AGVConfig.AGV_STATES
    })

@app.route('/api/send_request', methods=['POST'])
def send_request():
    """
    API nhận dữ liệu cấu hình khi nhấn nút Gửi.
    Lưu cấu hình vào config và bật cờ trang_thai_gui = True
    """
    data = request.json
    agv_name = data.get('agv_name')
    state = data.get('state')
    
    if agv_name and state:
        AGVConfig.thong_tin_da_chon[agv_name] = state
        AGVConfig.trang_thai_gui[agv_name] = True
        
        # Reset chỉ số về 0 khi gửi danh sách mới
        danh_sach = state.get("danh_sach_ke_da_chon", [])
        AGVConfig.chi_so_hang_hien_tai[agv_name] = 0
        if danh_sach and len(danh_sach) > 0:
            AGVConfig.gia_tri_hang_hien_tai[agv_name] = danh_sach[0]
            
            # Logic tìm điểm cuối cho phần tử đầu tiên (Index 0) ngay khi gửi
            diem_cuoi = ""
            for _, point_data in AGVConfig.BAN_DO_KE.items():
                for item in point_data:
                    # item cấu trúc ["TenKe", "TenDiem"]
                    if item[0] == danh_sach[0]:
                        diem_cuoi = item[1]
                        break
                if diem_cuoi != "":
                    break
            AGVConfig.diem_cuoi_gui_agv[agv_name] = diem_cuoi
            
        else:
            AGVConfig.gia_tri_hang_hien_tai[agv_name] = ""
            AGVConfig.diem_cuoi_gui_agv[agv_name] = ""
            
        update_agv_states() # Cập nhật AGV_STATES ngay sau khi thay đổi cấu hình
        return jsonify({'status': 'success', 'message': 'Đã gửi yêu cầu'})
    return jsonify({'status': 'error', 'message': 'Dữ liệu không hợp lệ'}), 400

@app.route('/api/map_image')
def map_image(): # This function is duplicated, consider removing one instance. 
    """
    API trả về ảnh bản đồ trực tiếp từ bộ nhớ (numpy array -> png).
    Không cần lưu file ra đĩa.
    """
    # Mã hóa ảnh numpy (BGR) sang định dạng PNG
    is_success, buffer = cv2.imencode(".png", AGVConfig.img)
    if is_success:
        return Response(buffer.tobytes(), mimetype='image/png')
    return "Error encoding image", 500

@app.route('/api/save_markers', methods=['POST'])
def save_markers():
    """Lưu danh sách các điểm đánh dấu (giá kệ) vào file JSON."""
    try:
        markers = request.json.get('markers', [])
        with open(AGVConfig.path_markers, 'w', encoding='utf-8') as f:
            json.dump(markers, f, ensure_ascii=False, indent=4)
        return jsonify({'status': 'success', 'message': 'Đã lưu bản đồ thành công!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_markers')
def get_markers():
    """Đọc danh sách các điểm đánh dấu từ file JSON."""
    if not os.path.exists(AGVConfig.path_markers):
        return jsonify({'markers': []})
    try:
        with open(AGVConfig.path_markers, 'r', encoding='utf-8') as f:
            markers = json.load(f)
        return jsonify({'markers': markers})
    except:
        return jsonify({'markers': []})

@app.route('/api/save_occupied_points', methods=['POST'])
def save_occupied_points():
    """Lưu cấu hình điểm chiếm dụng (khóa điểm)."""
    try:
        data = request.json.get('rules', {})
        AGVConfig.diem_chiem_dung = data
        with open(AGVConfig.path_diem_chiem_dung, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return jsonify({'status': 'success', 'message': 'Đã lưu cấu hình khóa điểm!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_occupied_points')
def get_occupied_points():
    """Lấy cấu hình điểm chiếm dụng."""
    if not os.path.exists(AGVConfig.path_diem_chiem_dung):
        return jsonify({})
    return jsonify(AGVConfig.diem_chiem_dung)

@app.route('/api/get_uploaded_files')
def get_uploaded_files():
    """Lấy danh sách các file đang nằm trong thư mục upload chờ được Apply."""
    files = os.listdir(AGVConfig.path_folder_upload)
    return jsonify({'files': files})

@app.route('/api/upload_update_file', methods=['POST'])
def upload_update_file():
    """API nhận file cập nhật (ví dụ từ AGV quét bản đồ gửi lên)."""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Không tìm thấy file'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'Tên file trống'}), 400

    save_path = os.path.join(AGVConfig.path_folder_upload, file.filename)
    file.save(save_path)
    return jsonify({'status': 'success', 'message': f'Đã tải lên {file.filename}'})

@app.route('/api/clear_upload_folder', methods=['POST'])
def clear_upload_folder():
    """API xóa sạch thư mục upload nếu người dùng muốn dọn dẹp thủ công."""
    try:
        for filename in os.listdir(AGVConfig.path_folder_upload):
            file_path = os.path.join(AGVConfig.path_folder_upload, filename)
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        return jsonify({'status': 'success', 'message': 'Đã dọn dẹp thư mục upload.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/apply_update', methods=['POST'])
def apply_update():
    """
    Thực hiện cập nhật file từ folder upload vào hệ thống và backup file cũ.
    """
    try:
        if not os.path.exists(AGVConfig.path_download_json):
            return jsonify({'status': 'error', 'message': 'Không tìm thấy file download.json cấu hình'}), 404

        with open(AGVConfig.path_download_json, 'r', encoding='utf-8') as f:
            config_update = json.load(f)

        master_ip = config_update.get('download_ip')
        master_port = config_update.get('port', 5000)
        files_to_update = config_update.get('files', [])
        updated_count = 0
        
        # Nếu có download_ip, thực hiện tải file từ máy đó về trước
        if master_ip:
            for item in files_to_update:
                target_rel_path = item['target'].lstrip('/')
                filename = item['name']
                remote_url = f"http://{master_ip}:{master_port}/api/download_update/{target_rel_path}"
                try:
                    r = requests.get(remote_url, timeout=10)
                    if r.status_code == 200:
                        with open(os.path.join(AGVConfig.path_folder_upload, filename), 'wb') as f:
                            f.write(r.content)
                    else:
                        return jsonify({'status': 'error', 'message': f"Lỗi {r.status_code} khi tải {filename}"}), 500
                except Exception as e:
                    return jsonify({'status': 'error', 'message': f"Không thể kết nối tới AGV {master_ip}: {str(e)}"}), 500

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(AGVConfig.path_backup, timestamp)
        os.makedirs(backup_dir, exist_ok=True)

        backup_manifest_entries = []

        for item in files_to_update:
            filename = item['name']
            # target_path là đường dẫn tương đối tính từ PATH_PHAN_MEM
            target_rel_path = item['target'].lstrip('/')
            source_path = os.path.join(AGVConfig.path_folder_upload, filename)
            final_target_path = os.path.join(AGVConfig.PATH_PHAN_MEM, target_rel_path)

            if os.path.exists(source_path):
                # 1. Backup file cũ nếu tồn tại
                if os.path.exists(final_target_path):
                    shutil.copy2(final_target_path, os.path.join(backup_dir, filename))
                    backup_manifest_entries.append({
                        "filename": filename,
                        "original_target_rel_path": target_rel_path
                    })
                
                # 2. Đảm bảo thư mục đích tồn tại
                os.makedirs(os.path.dirname(final_target_path), exist_ok=True)
                
                # 3. Ghi đè file mới
                shutil.move(source_path, final_target_path)
                
                updated_count += 1
        
        # Lưu backup_manifest.json nếu có file được backup
        if backup_manifest_entries:
            with open(os.path.join(backup_dir, "backup_manifest.json"), 'w', encoding='utf-8') as f:
                json.dump({"timestamp": timestamp, "files_backed_up": backup_manifest_entries}, f, indent=4, ensure_ascii=False)

        # Reload map nếu có cập nhật log_odds.npy
        if any(f['name'] == 'log_odds.npy' for f in files_to_update):
            if os.path.exists(AGVConfig.path_map):
                AGVConfig.img = config.get_occupancy_image(log_odds_map=np.load(AGVConfig.path_map))

        return jsonify({
            'status': 'success', 
            'message': f'Cập nhật thành công {updated_count} file. Bản cũ lưu tại {timestamp}'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/list_backups')
def list_backups():
    """
    API liệt kê tất cả các bản sao lưu có sẵn trong thư mục config.path_backup.
    Mỗi bản sao lưu là một thư mục có tên là timestamp.
    """
    backups = []
    if not os.path.exists(AGVConfig.path_backup):
        return jsonify(backups)

    for entry in os.listdir(AGVConfig.path_backup):
        backup_path = os.path.join(AGVConfig.path_backup, entry)
        if os.path.isdir(backup_path):
            manifest_path = os.path.join(backup_path, "backup_manifest.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                    backups.append({
                        "timestamp": manifest.get("timestamp", entry),
                        "files_backed_up": manifest.get("files_backed_up", [])
                    })
                except json.JSONDecodeError:
                    # Bỏ qua các thư mục không có manifest hợp lệ
                    pass
            else:
                # Nếu không có manifest, chỉ liệt kê các file có trong thư mục backup
                files_in_backup = [f for f in os.listdir(backup_path) if os.path.isfile(os.path.join(backup_path, f))]
                backups.append({
                    "timestamp": entry,
                    "files_backed_up": [{"filename": f, "original_target_rel_path": f} for f in files_in_backup]
                })
    
    # Sắp xếp theo timestamp mới nhất lên đầu
    backups.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(backups)

@app.route('/api/restore_backup', methods=['POST'])
def restore_backup():
    """
    API khôi phục một file cụ thể từ bản sao lưu.
    """
    data = request.json
    timestamp = data.get('timestamp')
    filename = data.get('filename')
    original_target_rel_path = data.get('original_target_rel_path')

    if not all([timestamp, filename, original_target_rel_path]):
        return jsonify({'status': 'error', 'message': 'Thiếu thông tin khôi phục'}), 400

    source_path = os.path.join(AGVConfig.path_backup, timestamp, filename)
    destination_path = os.path.join(AGVConfig.PATH_PHAN_MEM, original_target_rel_path)

    if not os.path.exists(source_path):
        return jsonify({'status': 'error', 'message': f'File backup không tồn tại: {source_path}'}), 404

    try:
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.copy2(source_path, destination_path)
        # Nếu là file bản đồ, cần nạp lại
        if filename == 'log_odds.npy':
            AGVConfig.reload_map()
        return jsonify({'status': 'success', 'message': f'Đã khôi phục {filename} từ bản sao lưu {timestamp}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Lỗi khi khôi phục file: {str(e)}'}), 500

@app.route('/api/deploy_to_all_agvs', methods=['POST'])
def deploy_to_all_agvs():
    """
    Lệnh này chạy trên Master Server. 
    Nó quét danh sách AGV_ENDPOINTS và ra lệnh cho các AGV đó gọi lại chính nó để cập nhật.
    """
    my_ip = get_local_ip()
    results = {}
    
    # Duyệt qua các AGV trong mạng (Sử dụng IP từ AGV_ENDPOINTS trong config)
    for agv_id, endpoint in AGVConfig.AGV_ENDPOINTS.items():
        # endpoint thường là http://IP:PORT/PC_sent_AGV, ta cần đổi sang /api/sync_from_master
        base_url = endpoint.rsplit('/', 1)[0].replace('PC_sent_AGV', '').rstrip('/')
        # Giả sử các AGV con cũng chạy API ở port 5000 hoặc cùng port với endpoint
        sync_url = f"{base_url}/api/sync_from_master" 
        
        try:
            resp = requests.post(sync_url, json={'master_ip': my_ip}, timeout=2)
            results[agv_id] = resp.json().get('message', 'OK')
        except Exception as e:
            results[agv_id] = f"Lỗi: {str(e)}"
            
    return jsonify({'status': 'success', 'details': results})

@app.route('/api/get_sync_manifest')
def get_sync_manifest():
    """API cho các AGV khác gọi để biết cần tải những file nào."""
    if os.path.exists(AGVConfig.path_download_json):
        return send_from_directory(os.path.dirname(AGVConfig.path_download_json), 'download.json')
    return jsonify({'files': []})

@app.route('/api/download_update/<path:filepath>')
def download_update_file_agv(filepath):
    """API cho các AGV khác tải file cập nhật."""
    return send_from_directory(AGVConfig.PATH_PHAN_MEM, filepath)

@app.route('/api/get_graph_data')
def get_graph_data():
    """
    API đọc file danh sách điểm và danh sách đường, gửi về client cùng kích thước ảnh map.
    """
    points_map = {}
    paths_list = []
    h, w = AGVConfig.img.shape[:2]

    try:
        # 1. Đọc danh sách ĐIỂM
        # print(AGVConfig.path_danh_sach_diem, os.path.exists(AGVConfig.path_danh_sach_diem))
        if os.path.exists(AGVConfig.path_danh_sach_diem):
            with open(AGVConfig.path_danh_sach_diem, 'r', encoding='utf-8') as f:
                data_points = json.load(f)
                for key, value in data_points.items():
                    # Kiểm tra định dạng điểm: [x, y, ...]
                    if isinstance(value, list) and len(value) >= 2 and isinstance(value[0], (int, float)):
                        # Chuyển đổi mm sang pixel
                        points_map[key] = {"name": key, "x": float(value[0]), "y": float(value[1])}
        print("Danh sách điểm đã đọc:", points_map)
        # 2. Đọc danh sách ĐƯỜNG
        if os.path.exists(AGVConfig.path_danh_sach_duong):
            with open(AGVConfig.path_danh_sach_duong, 'r', encoding='utf-8') as f:
                data_paths = json.load(f)
                for key, value in data_paths.items():
                    # Kiểm tra định dạng đường mới: [["Start", "End"], "type", "ControlPoint" (nếu có)]
                    if isinstance(value, list) and len(value) >= 1 and isinstance(value[0], list) and len(value[0]) >= 2:
                        nodes = value[0]
                        start_node = nodes[0]
                        end_node = nodes[1]
                        path_type = value[1] if len(value) > 1 else "none"
                        control_node = value[2] if len(value) > 2 else None

                        if start_node in points_map and end_node in points_map:
                            path_item = {
                                "start": points_map[start_node],
                                "end": points_map[end_node],
                                "type": path_type,
                                "start_node": start_node,
                                "end_node": end_node
                            }
                            if path_type == "curve" and control_node in points_map:
                                path_item["control"] = points_map[control_node]
                            paths_list.append(path_item)
        print("Danh sách đường đã đọc:", paths_list)
        return jsonify({'points': list(points_map.values()), 'paths': paths_list, 'dims': [w, h]})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_connected_agvs')
def get_connected_agvs():
    """API trả về danh sách các AGV đang kết nối và thời gian phản hồi cuối."""
    now = time.time()
    data = []
    for agv_id in AGVConfig.DANH_SACH_AGV:
        info = AGVConfig.danh_sach_ip_ket_noi.get(agv_id)
        
        if info:
            address = info["address"]
            seconds_ago = int(now - info["last_seen"])
        else:
            # Lấy địa chỉ từ cấu hình endpoint nếu AGV chưa từng phản hồi
            endpoint = AGVConfig.AGV_ENDPOINTS.get(agv_id)
            if endpoint:
                address = urlparse(endpoint).netloc
            else:
                address = "Chưa cấu hình"
            seconds_ago = 999999 # Giá trị lớn biểu thị chưa bao giờ kết nối
            
        data.append({
            "id": agv_id,
            "address": address,
            "seconds_ago": seconds_ago
        })
    return jsonify(data)

@app.route('/api/send_complete', methods=['POST'])
def send_complete():
    """
    API nhận tín hiệu hoàn thành từ nút nhấn giả lập.
    """
    data = request.json
    agv_name = data.get('agv_name')
    
    if agv_name:
        AGVConfig.trang_thai_hoan_thanh[agv_name] = True
        
        # Logic: Tăng index lên 1, nếu hết danh sách thì quay về 0 (vòng lặp)
        danh_sach = AGVConfig.thong_tin_da_chon[agv_name].get("danh_sach_ke_da_chon", [])
        if danh_sach and len(danh_sach) > 0:
            hien_tai = AGVConfig.chi_so_hang_hien_tai.get(agv_name, 0)
            tiep_theo = (hien_tai + 1) % len(danh_sach) # Phép chia lấy dư để tạo vòng lặp
            
            AGVConfig.chi_so_hang_hien_tai[agv_name] = tiep_theo # index ví dụ  0, 1, 2... và sẽ quay về 0 sau khi vượt quá độ dài danh sách
            AGVConfig.gia_tri_hang_hien_tai[agv_name] = danh_sach[tiep_theo] # giá trị hàng hiện tại (ví dụ: "B01")

            # tìm điểm tương ứng với giá hàng tiếp theo để gửi cho AGV từ BAN_DO_KE
            dich_den = ""
            for point_name, point_data in AGVConfig.BAN_DO_KE.items():
                for item in point_data:
                    if item[0] == danh_sach[tiep_theo]: # nếu tên giá hàng trùng với tên trong BAN_DO_KE
                        dich_den = item[1] # lấy điểm tương ứng để gửi cho AGV
                        break
                if dich_den != "":
                    break

            if dich_den != "":
                AGVConfig.diem_cuoi_gui_agv[agv_name] = dich_den


            print(f"{agv_name} hoàn thành. Chuyển sang {danh_sach[tiep_theo]} (index {tiep_theo})")

            update_agv_states() # Cập nhật AGV_STATES sau khi đổi đích đến
            
            return jsonify({'status': 'success', 'message': f'{agv_name} hoàn thành. Tiếp theo: {danh_sach[tiep_theo]}'})
            
        return jsonify({'status': 'success', 'message': f'{agv_name} đã hoàn thành (không có danh sách)'})
    return jsonify({'status': 'error', 'message': 'Thiếu tên AGV'}), 400




# {'W3': ['X3', 'W4', 'H213'], 'X3': ['W3'], 'W4': ['W3', 'X4'], 'X4': ['W4'], 'H213': ['W3', 'H210', 'G75'], 'G21': ['G31', 'G11', 'C1'], 'G31': ['G21', 'G41', 'C1'], 'G41': ['G31', 'G51'], 
#  'G12': ['G22', 'H04', 'H14'], 'G22': ['G12', 'G32'], 'G32': ['G22', 'G42'], 'G42': ['G32', 'G52'], 'G52': ['G42', 'G62'], 'G53': ['G43', 'G63'], 'G43': ['G53', 'G33'], 'G33': ['G43', 'G23'], 
#  'G23': ['G33', 'G13'], 'G13': ['G23', 'H17'], 'H17': ['G13', 'H07', 'X2', 'X1'], 'H110': ['G14', 'H010', 'X2', 'C2'], 'G14': ['H110', 'G24'], 'G24': ['G14', 'G44'], 'G44': ['G24', 'G54'], 
#  'G54': ['G44', 'G64'], 'G55': ['G45', 'G65'], 'G45': ['G55', 'G35'], 'G35': ['G45', 'G25', 'C2'], 'G25': ['G35', 'G15', 'C2'], 'H21': ['H24', 'G71'], 'H24': ['H21', 'H27', 'G72'], 
#  'H27': ['H24', 'H210', 'G73'], 'H210': ['H27', 'H213', 'G74'], 'H07': ['H17', 'H05', 'H010'], 'H010': ['H110', 'H07', 'C2'], 'X2': ['H17', 'H110', 'W2'], 'W2': ['X2', 'W1'], 
#  'H05': ['H07', 'H04', 'W1'], 'H04': ['H05', 'G12', 'C1'], 'H14': ['G12', 'X1', 'C1'], 'W1': ['H05', 'X1', 'W2'], 'X1': ['W1', 'H14', 'H17'], 'G11': ['G21', 'C1'], 'G51': ['G41', 'G61'], 
#  'G61': ['G51', 'G71'], 'G71': ['G61', 'H21'], 'G62': ['G52', 'G72'], 'G72': ['H24', 'G62'], 'G63': ['G53', 'G73'], 'G73': ['G63', 'H27'], 'G64': ['G54', 'G74'], 'G74': ['G64', 'H210'], 
#  'G65': ['G55', 'G75'], 'G75': ['G65', 'H213'], 'G15': ['G25', 'C2'], 'C1': ['H14', 'H04', 'G11', 'G21', 'G31'], 'C2': ['H110', 'H010', 'G25', 'G15', 'G35']}

# 1. Create GraphManager and populate it from loaded data
graph_manager = GraphManager()
fleet = None
visualizer = None
test_icp_simulation_loop = True

def icp_simulation_loop():
    global graph_manager, fleet, visualizer
    while True:
        if test_icp_simulation_loop == True:
            if AGVConfig_2.danh_sach_diem is None:
                AGVConfig_2.danh_sach_diem = tim_duong_di.load_points_route(AGVConfig.ten_danh_sach_diem)

                AGVConfig_2.danh_sach_diem_mm = AGVConfig_2.danh_sach_diem.copy()
                map_size_mm=100000.0                             # Kích thước tổng của bản đồ (mm).
                resolution_mm= 20                             # Độ phân giải của bản đồ (mm/pixel).
                # occupancy grid (pixels)
                pixels = int(np.ceil(map_size_mm / resolution_mm))
                center_px = (pixels // 2, pixels // 2)
                # Chuyển đổi toàn bộ danh_sach_diem (bao gồm cả các điểm control của curve) sang tọa độ mm
                for name, val in AGVConfig_2.danh_sach_diem_mm.items():
                    if isinstance(val, list) and len(val) >= 2:
                        px, py = val[0], val[1]
                        val[0] = (px - center_px[0]) * resolution_mm
                        val[1] = (center_px[1] - py) * resolution_mm

                print("Danh sách điểm đã nạp:", AGVConfig_2.danh_sach_diem_mm)
            if AGVConfig_2.danh_sach_duong is None:
                AGVConfig_2.danh_sach_duong = tim_duong_di.load_paths_route(AGVConfig.ten_danh_sach_duong, AGVConfig_2.danh_sach_diem)
                print("Danh sách đường đã nạp:", AGVConfig_2.danh_sach_duong)
            # if AGVConfig_2.graph is None:
            #     # Xác định các điểm quan trọng không được phép gộp (ví dụ: các điểm đích từ BAN_DO_KE)
            #     must_keep = set()
            #     for shelf_list in AGVConfig.BAN_DO_KE.values():
            #         for item in shelf_list:
            #             must_keep.add(item[1]) # item[1] là tên điểm trong danh_sach_diem
                
            #     AGVConfig_2.graph = tim_duong_di.tao_graph_cai_tien(AGVConfig_2.danh_sach_duong, AGVConfig_2.danh_sach_diem, must_keep)

        # agv_ids = AGVConfig.DANH_SACH_AGV
        # data_agv = {"agv1": {"start": "G21", "goal": "G42"},
        #             "agv2": {"start": "G22", "goal": "G41"},
        #             "agv3": {"start": "G23", "goal": "G44"},
        #             "agv4": {"start": "G24", "goal": "G53"},
        #             "agv5": {"start": "G25", "goal": "G24"},
        #             "agv6": {"start": "G74", "goal": "X3"},
        #             "agv7": {"start": "G75", "goal": "G65"}
        #             }
        
        # AGV_STATES = {
        #                 agv: {
        #                     "thong_tin_agv": {
        #                                         "diem_vua_di_qua": "",
        #                                         "diem_tiep_theo": "",
        #                                         "diem_cuoi": "",
        #                                         "toa_do": {"x": 0, "y": 0},
        #                                         "trang_thai_nang_ha": "ha",
        #                                         "goc_agv": 0,
        #                                         "message": "None",
        #                                         "danh_sach_duong_di": [],
        #                                         "da_den_dich": 0,
        #                                         "stop": False
        #                                     },
        #                     "dieu_khien_agv": {
        #                                         "diem_cuoi": "",
        #                                         "yeu_cau_gui_agv": "",
        #                                         "danh_sach_duong_di": [],
        #                                         "stop": False
        #                                     }
        #                 } for agv in DANH_SACH_AGV
        #             }

        id_agvs = ["agv1", "agv2", "agv3", "agv4", "agv5", "agv6", "agv7"]
        data_agv = {}
        for agv in id_agvs:
            if agv not in data_agv:
                data_agv[agv] = {}
            if AGVConfig.AGV_STATES[agv]["thong_tin_agv"]["diem_tiep_theo"] == "":
                data_agv[agv]["start"] = AGVConfig.AGV_STATES[agv]["thong_tin_agv"]["diem_vua_di_qua"]
            else:
                data_agv[agv]["start"] = AGVConfig.AGV_STATES[agv]["thong_tin_agv"]["diem_tiep_theo"]
            data_agv[agv]["goal"] = AGVConfig.AGV_STATES[agv]["dieu_khien_agv"]["diem_cuoi"]

        
        # test với số liệu
        # data_agv = {"agv1": {"start": "G21", "goal": ""},
        #             "agv2": {"start": "G22", "goal": "G41"},
        #             "agv3": {"start": "G23", "goal": "G44"},
        #             "agv4": {"start": "G24", "goal": "G53"},
        #             "agv5": {"start": "G25", "goal": "G24"},
        #             "agv6": {"start": "G74", "goal": "G74"},
        #             "agv7": {"start": "G75", "goal": "G65"}
        #             }

        # print("data_---------agv", data_agv)
        output_cbs = cbs.main(data_agv, AGVConfig_2.danh_sach_diem_mm, AGVConfig_2.danh_sach_duong)
        # print("data cbs \n", output_cbs,"\n","data agv \n",data_agv)
        # {'schedule': {  'agv3': [{'t': 0, 'x': -13460, 'y': 2480, 'd': 0, 'name': 'G23'}, 
        #                        {'t': 2, 'x': -16100, 'y': 2420, 'd': np.float64(-177.99044618697886), 'name': 'H17'}, 
        #                        {'t': 4, 'x': -16000, 'y': -280, 'd': np.float64(-86.47854662307776), 'name': 'H110'}, 
        #                        {'t': 8, 'x': -8460, 'y': -160, 'd': np.float64(0.8363753254224154), 'name': 'G44'}], 
        #                 'agv1': [{'t': 0, 'x': -13600, 'y': 7940, 'd': 0, 'name': 'G21'}, 
        #                        {'t': 1, 'x': -13300, 'y': 7940, 'd': np.float64(0.0), 'name': 'C1'}, 
        #                        {'t': 2, 'x': -16140, 'y': 5120, 'd': np.float64(-135.2024577422182), 'name': 'H14'}, 
        #                        {'t': 6, 'x': -9040, 'y': 5320, 'd': np.float64(1.893385845746274), 'name': 'G42'}], 
        #                 'agv2': [{'t': 0, 'x': -13540, 'y': 5200, 'd': 0, 'name': 'G22'}, 
        #                          {'t': 6, 'x': 340, 'y': 5560, 'd': np.float64(1.4688007143858246), 'name': 'H24'}, 
        #                          {'t': 7, 'x': 280, 'y': 8300, 'd': np.float64(91.25445162268154), 'name': 'H21'}, 
        #                          {'t': 11, 'x': -9220, 'y': 8060, 'd': np.float64(-178.5436413656603), 'name': 'G41'}]}, 
        #   'cost': 12}
        if output_cbs is not None:
            schedule = output_cbs["schedule"]

            cost = output_cbs["cost"]

            danh_sach_t = []
            for agv_id in id_agvs:
                if agv_id in schedule:
                    if len(schedule[agv_id]) > 1:
                        danh_sach_t.append(schedule[agv_id][1]["t"])
            if len(danh_sach_t) == 0:
                stt_t = -1
            elif len(danh_sach_t) == 1:
                stt_t = danh_sach_t[0]
            else:
                stt_t = min(danh_sach_t)


            for agv_id in id_agvs:
                path_agv = []
                if agv_id in schedule:
                    if len(schedule[agv_id]) == 1:
                        path_agv = [schedule[agv_id][0]["name"]]
                    elif len(schedule[agv_id]) > 1:
                        if schedule[agv_id][1]["t"] == stt_t:
                            path_agv = [schedule[agv_id][0]["name"], schedule[agv_id][1]["name"]]
                print("-------", agv_id, path_agv)
                AGVConfig.AGV_STATES[agv_id]["dieu_khien_agv"]["danh_sach_duong_di"] = path_agv
                if len(path_agv) == 0:
                    AGVConfig.AGV_STATES[agv_id]["dieu_khien_agv"]["stop"] = True
                    print("schedule", schedule)
                else:
                    AGVConfig.AGV_STATES[agv_id]["dieu_khien_agv"]["stop"] = False
        # print(AGVConfig.AGV_STATES)
        




        # if AGVConfig_2.danh_sach_diem is not None and AGVConfig_2.danh_sach_duong is not None and AGVConfig_2.setup_manager == False:
        #     AGVConfig_2.setup_manager = True
            
        #     graph_manager.graph = AGVConfig_2.graph
        #     graph_manager.positions = {name: (data[0], data[1]) for name, data in AGVConfig_2.danh_sach_diem.items()}

        #     fleet = FleetLogicRealTime(graph_manager, agv_ids, AGVConfig.diem_chiem_dung)
        #     # visualizer = AGVVisualizer(graph_manager, agv_ids)
        # if fleet is not None:
        #     if AGVConfig.AGV_STATES["agv1"]["thong_tin_agv"]["diem_tiep_theo"] == "":
        #         vi_tri_hien_tai_agv1 = AGVConfig.AGV_STATES["agv1"]["thong_tin_agv"]["diem_vua_di_qua"]
        #     else:
        #         vi_tri_hien_tai_agv1 = AGVConfig.AGV_STATES["agv1"]["thong_tin_agv"]["diem_tiep_theo"]
        #     # vi_tri_hien_tai_agv2 = AGVConfig.AGV_STATES["agv2"]["thong_tin_agv"]["diem_vua_di_qua"]
        #     # vi_tri_hien_tai_agv1 = "C1"
        #     vi_tri_hien_tai_agv2 = ""
        #     vi_tri_hien_tai_agv3 = ""
        #     current_telemetry = [
        #         {"agv_id": "agv1", "current_node": vi_tri_hien_tai_agv1, "status": "IDLE"},
        #         {"agv_id": "agv2", "current_node": vi_tri_hien_tai_agv2, "status": "IDLE"},
        #         {"agv_id": "agv3", "current_node": vi_tri_hien_tai_agv3, "status": "IDLE"},
        #         # {"agv_id": "agv4", "current_node": vi_tri_hien_tai_agv4, "status": "IDLE"},
        #         # {"agv_id": "agv5", "current_node": vi_tri_hien_tai_agv5, "status": "IDLE"},
        #         # {"agv_id": "agv6", "current_node": vi_tri_hien_tai_agv6, "status": "IDLE"},
        #         # {"agv_id": "agv7", "current_node": vi_tri_hien_tai_agv7, "status": "IDLE"},
        #     ]
        #     # print(AGVConfig.AGV_STATES)
        #     dich_den_agv1 = AGVConfig.AGV_STATES["agv1"]["thong_tin_agv"]["diem_cuoi"]
        #     # dich_den_agv2 = AGVConfig.AGV_STATES["agv2"]["thong_tin_agv"]["diem_cuoi"]
        #     # dich_den_agv1 = "G42"
        #     dich_den_agv2 = ""
        #     dich_den_agv3 = ""
        #     initial_jobs = [
        #         {"agv_id": "agv1", "goal": dich_den_agv1},
        #         {"agv_id": "agv2", "goal": dich_den_agv2},
        #         {"agv_id": "agv3", "goal": dich_den_agv3},
        #         # {"agv_id": "agv4", "goal": "B1"},
        #         # {"agv_id": "agv5", "goal": "E1"},
        #         # {"agv_id": "agv6", "goal": "E3"},
        #         # {"agv_id": "agv7", "goal": "E4"},
        #     ]

        #     input_data = {"telemetry": current_telemetry, "jobs": initial_jobs}
        #     # print("\nINPUT CHO VÒNG LẶP:", input_data)

        #     commands = fleet.run_cycle(input_data)

        #     paths_agv = []
        #     stop = False
        #     for agv_id in agv_ids:
        #         cmd = commands.get(agv_id, {})
        #         current_agv_data = fleet.agvs[agv_id]
                
        #         # Mặc định lấy vị trí hiện tại
        #         current_node = current_agv_data["current_node"]
                
        #         if cmd.get("command") == "DI_CHUYEN":
        #             path = cmd.get("path", [])
        #             paths_agv = path
        #             print(f"DEBUG: AGV {agv_id} received DI_CHUYEN command with path: {path}")

        #             if len(path) > 0:
        #                 current_node = path[1] if len(path) > 1 else path[0]
        #                 # Nếu node vừa tới là đích của path hiện tại
        #                 if current_node == current_agv_data["path"][-1]:
        #                     status = "da_den_dich"
        #                     stop = True
        #                     print(f"OUTPUT: {agv_id} DA_DEN_DICH {current_node}")
        #                 else:
        #                     status = "dang_di_chuyen"
        #             else:
        #                 stop = True
        #                 status = "tam_dung"
        #         else:
        #             print(f"DEBUG: AGV {agv_id} stop")
        #             stop = True
        #             # KIỂM TRA TẠI ĐÂY: 
        #             # Nếu không có lệnh di chuyển nhưng node hiện tại trùng với đích cũ
        #             if current_agv_data["goal"] and current_node == current_agv_data["goal"]:
        #                 status = "da_den_dich"
        #             elif cmd.get("command") == "TAM_DUNG":
        #                 status = "tam_dung"
        #             else:
        #                 status = "da_den_dich" if current_agv_data["path"] == [] else "dang_cho"
                
        #         AGVConfig.AGV_STATES[agv_id]["dieu_khien_agv"]["danh_sach_duong_di"] = paths_agv
                # AGVConfig.AGV_STATES[agv_id]["stop"] = stop
                # new_telemetry.append({
                #     "agv_id": agv_id, 
                #     "current_node": current_node, 
                #     "status": status
                # })

            # current_telemetry = new_telemetry
            # [{'agv_id': 'agv1', 'current_node': 'P19', 'status': 'dang_di_chuyen'}, 
            #  {'agv_id': 'agv2', 'current_node': 'P81', 'status': 'dang_di_chuyen'}]
            # ... (phần in và sleep giữ nguyên)



        # print(AGVConfig.che_do_tao_ban_do)
        time.sleep(1) # Tăng tần suất kiểm tra (10Hz) để xử lý watchdog kịp thời


if __name__ == '__main__':
    # Đảm bảo luồng mô phỏng chỉ chạy 1 lần trong tiến trình xử lý chính
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Thread(target=icp_simulation_loop, daemon=True).start()
    # Chạy server với debug=True để tự động reload khi sửa code
    app.run(host='0.0.0.0', port=5000, debug=True)