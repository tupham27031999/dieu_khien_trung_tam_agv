import math
import heapq
import os
import time
import json
import config_2 as cfg
from mo_phong_agv.fleet_logic_thuc_te import FleetLogicRealTime
from mo_phong_agv.simulation import AGVVisualizer
from mo_phong_agv.graph_manager import GraphManager



def load_points_route(filename): # Change parameter name to match the variable rule
    danh_sach_diem = {}
    name_file = filename.split(".")[0]
    filepath = cfg.PATH_POINTS_DIR + "/" + name_file + ".json"
    print(filepath)
    if not os.path.exists(filepath):
        print("e1")
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            loaded_points = json.load(f)
        danh_sach_diem = loaded_points
    return danh_sach_diem


def load_paths_route(filename, danh_sach_diem=None):
    danh_sach_duong = {}
    name_file = filename.split(".")[0]
    filepath = cfg.PATH_PATHS_DIR + "/" + name_file + ".json"
    print(filepath)
    if not os.path.exists(filepath):
        print("e2")
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            loaded_paths = json.load(f)
        
        # Validate if points for these paths exist in current danh_sach_diem
        valid_paths = {}
        for path_name, path_data in loaded_paths.items():
            (p1_name, p2_name) = path_data[0]
            direction = path_data[1]
            if p1_name in danh_sach_diem and p2_name in danh_sach_diem:
                valid_paths[path_name] = [[p1_name, p2_name], direction]
            else:
                print(f"Warning: Path '{path_name}' skipped during load. Point(s) '{p1_name}' or '{p2_name}' not in current point list.")
        
        danh_sach_duong = valid_paths
    return danh_sach_duong


# --- Tạo graph có hướng ---
def tao_graph(danh_sach_duong):
    graph = {}
    for key, value in danh_sach_duong.items():
        (a, b), direction = value

        if direction == "none" or direction == "curve":  # Đường 2 chiều
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, []).append(a)
        else:
            # direction dạng "P1-P4" -> chỉ có hướng P1 → P4
            start, end = direction.split("-")
            graph.setdefault(start, []).append(end)
    return graph
# def tao_duong_di_cho_agv():
    
def creat_data_graph():
    load_points_route("t2.json")
    load_paths_route("t2.json")
    tao_graph()
    # print(graph)

# creat_data_grap()



if __name__ == "__main__":
    diem_chiem_dung = {}

    # 1. Create GraphManager and populate it from loaded data
    graph_manager = GraphManager()
    graph_manager.graph = tao_graph()
    graph_manager.positions = {name: (data[0], data[1]) for name, data in danh_sach_diem.items()}

    # # 2. Khởi tạo Fleet Logic và Visualizer
    # agv_ids = ["agv1", "agv2", "agv3"]
    # fleet = FleetLogicRealTime(graph_manager, agv_ids, diem_chiem_dung)
    # visualizer = AGVVisualizer(graph_manager, agv_ids)




    # 2. Khởi tạo Fleet Logic và Visualizer
    # agv_ids = ["agv1", "agv2", "agv3"]
    agv_ids = ["agv1"]
    fleet = FleetLogicRealTime(graph_manager, agv_ids, diem_chiem_dung)
    visualizer = AGVVisualizer(graph_manager, agv_ids)

    # 3. Dữ liệu cố định ban đầu
    current_telemetry = [
        {"agv_id": "agv1", "current_node": "X1", "status": "IDLE"},
        # {"agv_id": "agv2", "current_node": "A1", "status": "IDLE"},
        # {"agv_id": "agv3", "current_node": "D2", "status": "IDLE"},
    ]
    initial_jobs = [
        {"agv_id": "agv1", "goal": "X2"},
    #     {"agv_id": "agv2", "goal": "E2"},
    #     {"agv_id": "agv3", "goal": "B2"},
    ]

    print("--- BẮT ĐẦU ĐIỀU PHỐI VÒNG LẶP ---")
    
    running = True
    active_jobs = initial_jobs
    
    while running:
        input_data = {"telemetry": current_telemetry, "jobs": active_jobs}
        print("\nINPUT CHO VÒNG LẶP:", input_data)

        commands = fleet.run_cycle(input_data)

        new_telemetry = []
        for agv_id in agv_ids:
            cmd = commands.get(agv_id, {})
            current_agv_data = fleet.agvs[agv_id]
            
            # Mặc định lấy vị trí hiện tại
            current_node = current_agv_data["current_node"]
            
            if cmd.get("command") == "DI_CHUYEN":
                path = cmd.get("path", [])
                print(f"DEBUG: AGV {agv_id} received DI_CHUYEN command with path: {path}")
                current_node = path[1] if len(path) > 1 else path[0]
                
                # Nếu node vừa tới là đích của path hiện tại
                if current_node == current_agv_data["path"][-1]:
                    status = "da_den_dich"
                    print(f"OUTPUT: {agv_id} DA_DEN_DICH {current_node}")
                else:
                    status = "dang_di_chuyen"
            else:
                # KIỂM TRA TẠI ĐÂY: 
                # Nếu không có lệnh di chuyển nhưng node hiện tại trùng với đích cũ
                if current_agv_data["goal"] and current_node == current_agv_data["goal"]:
                    status = "da_den_dich"
                elif cmd.get("command") == "TAM_DUNG":
                    status = "tam_dung"
                else:
                    status = "da_den_dich" if current_agv_data["path"] == [] else "dang_cho"

            new_telemetry.append({
                "agv_id": agv_id, 
                "current_node": current_node, 
                "status": status
            })

        current_telemetry = new_telemetry
        # ... (phần in và sleep giữ nguyên)
        
        
        print("\nTRANG_THAI_HE_THONG:", current_telemetry)
        time.sleep(1)
        if not visualizer.update_and_draw(current_telemetry, commands):
            break

        # if all(t["status"] in ["dang_cho", "da_den_dich"] for t in current_telemetry):
        #     print("--- TAT_CA_AGV_DA_HOAN_THANH ---")
        #     break

        # Cập nhật điều kiện thoát
        if all(t["status"] == "da_den_dich" for t in current_telemetry):
            print("--- TAT_CA_AGV_DA_DEN_DICH ---")
            time.sleep(2)
            break

    # pygame.quit()