import heapq
import random
import json
import pygame
import time

class FleetLogicRealTime:
    def __init__(self, graph_manager, initial_agv_ids, diem_chiem_dung = {}):
        # diem_chiem_dung = {
        #     ("A3", "A2"): [("A5", "A1")], # Khi đi từ A3 sang A2, khóa đường từ A5 -> A1
        #     ("A7", "A8"): [("B5", "B1")], 
        #     "P10": ["P48"],       # Bất kể đi từ đâu, hễ đích tiếp theo là P10 thì khóa P48
        # }
        self.diem_chiem_dung = diem_chiem_dung
        self.graph = graph_manager.graph
        self.positions = graph_manager.positions
        self.agvs = {}

        for agv_id in initial_agv_ids:
            self.agvs[agv_id] = {
                "agv_id": agv_id,
                "current_node": None,
                "goal": None,
                "path": [],
                "status": "chua_xac_dinh", # UNKNOWN -> chua_xac_dinh
                "obstacle_detected": False,
            }

    def update_agv_telemetry(self, telemetry_data):
        agv_id = telemetry_data.get("agv_id")
        if not agv_id or agv_id not in self.agvs:
            return

        agv_state = self.agvs[agv_id]
        agv_state["current_node"] = telemetry_data.get("current_node", agv_state["current_node"])
        agv_state["status"] = telemetry_data.get("status", agv_state["status"])
        agv_state["obstacle_detected"] = telemetry_data.get("obstacle_detected", False)

        # SỬA TẠI ĐÂY: Chấp nhận cả 'da_den_dich' để xác nhận hoàn thành
        trang_thai_nghi = ["dang_cho", "da_den_dich"]
        if agv_state["status"] in trang_thai_nghi and agv_state["path"]:
            if agv_state["current_node"] == agv_state["path"][-1]:
                print(f"[{agv_id}] xac_nhan_hoan_thanh tai {agv_state['current_node']}.")
                agv_state["path"] = []
                agv_state["goal"] = None

    def get_extra_reserved_nodes(self, from_node, to_node):
        extra = []
        # 1. Kiểm tra theo cặp (điểm hiện tại, điểm kế tiếp) - Ưu tiên cụ thể
        extra.extend(self.diem_chiem_dung.get((from_node, to_node), []))
        
        # 2. Kiểm tra chỉ dựa trên điểm kế tiếp (Tổng quát)
        extra.extend(self.diem_chiem_dung.get(to_node, []))

        #3. Kiểm tra chỉ dựa trên điểm hiện tại
        extra.extend(self.diem_chiem_dung.get(from_node, []))
        
        return list(set(extra)) # Trả về list không trùng lặp

    def process_and_generate_commands(self):
        commands_to_send = {}
        reserved_nodes, reserved_paths = self._get_all_reserved_nodes()

        for agv_id, agv in self.agvs.items():
            if not agv["path"] or not agv["current_node"]:
                continue

            if agv["current_node"] == agv["path"][-1]:
                continue

            try:
                current_index = agv["path"].index(agv["current_node"])
                next_node = agv["path"][current_index + 1]
            except (ValueError, IndexError):
                agv["path"] = []
                agv["goal"] = None
                commands_to_send[agv_id] = {"command": "DUNG_LAI", "reason": "loi_lo_trinh"}
                continue

            is_safe = True
            reason = ""

            if agv["obstacle_detected"]:
                is_safe = False
                reason = "vat_can_vat_ly"

            # 2️⃣ Kiểm tra Node bị AGV khác giữ
            if next_node in reserved_nodes and reserved_nodes[next_node] != agv_id:
                blocker_id = reserved_nodes[next_node]
                if agv_id > blocker_id:
                    is_safe = False
                    reason = f"nhuong_duong_cho_{blocker_id}"
            
            # 3️⃣ Kiểm tra Đường bị AGV khác khóa (Path Lock)
            current_move = (agv["current_node"], next_node)
            if is_safe and current_move in reserved_paths and reserved_paths[current_move] != agv_id:
                blocker_id = reserved_paths[current_move]
                if agv_id > blocker_id:
                    is_safe = False
                    reason = f"duong_bi_khoa_boi_{blocker_id}"

            if is_safe:
                remaining_path = agv["path"][current_index:]
                commands_to_send[agv_id] = {
                    "command": "DI_CHUYEN",
                    "path": remaining_path
                }
            else:
                commands_to_send[agv_id] = {
                    "command": "TAM_DUNG",
                    "at_node": agv["current_node"],
                    "reason": reason
                }
        return commands_to_send

    # ==========================================================
    # CÁC HÀM PHỤ TRỢ (PRIVATE)
    # ==========================================================
    def _a_star(self, start, goal, obstacles=None):
        if obstacles is None: obstacles = set()
        if start not in self.graph or goal not in self.graph: return None

        open_set = []
        heapq.heappush(open_set, (0, start))
        
        came_from = {}
        g_score = {node: float('inf') for node in self.graph}
        g_score[start] = 0
        f_score = {node: float('inf') for node in self.graph}
        f_score[start] = self._heuristic(start, goal)

        while open_set:
            _, current = heapq.heappop(open_set)

            if current == goal:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.append(start)
                return path[::-1]
            
            for neighbor in self.graph.get(current, []):
                if neighbor in obstacles:
                    continue
                
                tentative_g_score = g_score[current] + 1
                if tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = tentative_g_score + self._heuristic(neighbor, goal)
                    if neighbor not in [i[1] for i in open_set]:
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
        return None

    def _heuristic(self, u, v):
        pos_u = self.positions.get(u)
        pos_v = self.positions.get(v)
        if not pos_u or not pos_v: return float('inf')
        return ((pos_u[0] - pos_v[0])**2 + (pos_u[1] - pos_v[1])**2) ** 0.5

    def _get_static_obstacles(self, exclude_agv_id=None):
        """Lấy vị trí hiện tại của các AGV khác làm vật cản tĩnh."""
        obstacles = set()
        for agv_id, agv in self.agvs.items():
            if agv_id != exclude_agv_id and agv["current_node"]:
                obstacles.add(agv["current_node"])
        return obstacles

    def _get_all_reserved_nodes(self):
        """Lấy node hiện tại và node tiếp theo của tất cả AGV để tránh va chạm."""
        reserved_nodes = {}
        reserved_paths = {}
        # Sắp xếp để đảm bảo AGV có ID nhỏ hơn được ưu tiên khi chiếm node
        sorted_agvs = sorted(self.agvs.items())

        for agv_id, agv in sorted_agvs:
            if not agv["current_node"]: continue
            
            # Node hiện tại luôn bị chiếm
            if agv["current_node"] not in reserved_nodes:
                reserved_nodes[agv["current_node"]] = agv_id
            
            # Node tiếp theo cũng được "đặt trước"
            if agv["path"]:
                try:
                    current_path_index = agv["path"].index(agv["current_node"])
                    if current_path_index + 1 < len(agv["path"]):
                        next_node = agv["path"][current_path_index + 1]
                        # chiếm node kế tiếp
                        if next_node not in reserved_nodes:
                            reserved_nodes[next_node] = agv_id

                        # Lấy danh sách khóa mở rộng (có thể là điểm hoặc đường)
                        extras = self.get_extra_reserved_nodes(
                            agv["current_node"],
                            next_node
                        )
                        
                        for item in extras:
                            # Nếu item là một list/tuple có 2 phần tử -> Khóa đường
                            if isinstance(item, (list, tuple)) and len(item) == 2:
                                path_tuple = tuple(item)
                                if path_tuple not in reserved_paths:
                                    reserved_paths[path_tuple] = agv_id
                            else:
                                # Ngược lại là khóa điểm
                                if item not in reserved_nodes:
                                    reserved_nodes[item] = agv_id

                except (ValueError, IndexError):
                    pass
        return reserved_nodes, reserved_paths

    def assign_job(self, agv_id, goal_node):
        if agv_id not in self.agvs: return False
        agv = self.agvs[agv_id]
        if not agv["current_node"]: return False

        obstacles = self._get_static_obstacles(exclude_agv_id=agv_id)
        path = self._a_star(agv["current_node"], goal_node, obstacles)

        if path and len(path) > 1:
            agv["goal"] = goal_node
            agv["path"] = path
            # print(f"[{agv_id}] nhan_viec: {agv['current_node']} -> {goal_node}")
            return True
        return False
    
    def run_cycle(self, input_data):
        for packet in input_data.get("telemetry", []):
            self.update_agv_telemetry(packet)
        for job in input_data.get("jobs", []):
            self.assign_job(job.get("agv_id"), job.get("goal"))
        return self.process_and_generate_commands()

# ==========================================================
# PHẦN CHẠY THỬ NGHIỆM (DEMO CHO 1 VÒNG LẶP)
# ==========================================================
if __name__ == "__main__":
    from graph_manager import GraphManager
    from simulation import AGVVisualizer  # Import file vừa tạo
    import json

    graph = GraphManager()

    # tạo map mẫu
    graph.add_node("A1", (100, 100)), graph.add_node("A2", (200, 100)), graph.add_node("A3", (300, 100)), graph.add_node("A4", (400, 100)), graph.add_node("A5", (500, 100)), graph.add_node("A6", (600, 100)), graph.add_node("A7", (700, 100)), graph.add_node("A8", (800, 100)), graph.add_node("A9", (900, 100))
    graph.add_node("B1", (100, 200)), graph.add_node("B2", (200, 200)), graph.add_node("B3", (300, 200)), graph.add_node("B4", (400, 200)), graph.add_node("B5", (500, 200)), graph.add_node("B6", (600, 200)), graph.add_node("B7", (700, 200)), graph.add_node("B8", (800, 200)), graph.add_node("B9", (900, 200))
    graph.add_node("C1", (100, 300)), graph.add_node("C2", (200, 300)), graph.add_node("C3", (300, 300)), graph.add_node("C4", (400, 300)), graph.add_node("C5", (500, 300)), graph.add_node("C6", (600, 300)), graph.add_node("C7", (700, 300)), graph.add_node("C8", (800, 300)), graph.add_node("C9", (900, 300))
    graph.add_node("D1", (100, 400)), graph.add_node("D2", (200, 400)), graph.add_node("D3", (300, 400)), graph.add_node("D4", (400, 400)), graph.add_node("D5", (500, 400)), graph.add_node("D6", (600, 400)), graph.add_node("D7", (700, 400)), graph.add_node("D8", (800, 400)), graph.add_node("D9", (900, 400))
    graph.add_node("E1", (100, 500)), graph.add_node("E2", (200, 500)), graph.add_node("E3", (300, 500)), graph.add_node("E4", (400, 500)), graph.add_node("E5", (500, 500)), graph.add_node("E6", (600, 500)), graph.add_node("E7", (700, 500)), graph.add_node("E8", (800, 500)), graph.add_node("E9", (900, 500))
    # graph.add_node("F1", (100, 600)), graph.add_node("F2", (200, 600)), graph.add_node("F3", (300, 600)), graph.add_node("F4", (400, 600)), graph.add_node("F5", (500, 600)), graph.add_node("F6", (600, 600)), graph.add_node("F7", (700, 600)), graph.add_node("F8", (800, 600)), graph.add_node("F9", (900, 600))
    # graph.add_node("G1", (100, 700)), graph.add_node("G2", (200, 700)), graph.add_node("G3", (300, 700)), graph.add_node("G4", (400, 700)), graph.add_node("G5", (500, 700)), graph.add_node("G6", (600, 700)), graph.add_node("G7", (700, 700)), graph.add_node("G8", (800, 700)), graph.add_node("G9", (900, 700))

    graph.add_edge("A1", "A2"), graph.add_edge("A2", "A3")
    graph.add_edge("B1", "B2"), graph.add_edge("B2", "B3")
    graph.add_edge("C1", "C2"), graph.add_edge("C2", "C3")
    graph.add_edge("D1", "D2"), graph.add_edge("D2", "D3")
    graph.add_edge("E1", "E2"), graph.add_edge("E2", "E3")
    # graph.add_edge("F1", "F2"), graph.add_edge("F2", "F3")
    # graph.add_edge("G1", "G2"), graph.add_edge("G2", "G3")

    graph.add_edge("A7", "A8"), graph.add_edge("A8", "A9")
    graph.add_edge("B7", "B8"), graph.add_edge("B8", "B9")
    graph.add_edge("C7", "C8"), graph.add_edge("C8", "C9")
    graph.add_edge("D7", "D8"), graph.add_edge("D8", "D9")
    graph.add_edge("E7", "E8"), graph.add_edge("E8", "E9")
    # graph.add_edge("F7", "F8"), graph.add_edge("F8", "F9")
    # graph.add_edge("G7", "G8"), graph.add_edge("G8", "G9")

    graph.add_edge("A1", "B2"), graph.add_edge("A2", "B1")
    graph.add_edge("B1", "C2"), graph.add_edge("B2", "C1")
    graph.add_edge("C1", "D2"), graph.add_edge("C2", "D1")
    graph.add_edge("D1", "E2"), graph.add_edge("D2", "E1")
    # graph.add_edge("E1", "F2"), graph.add_edge("E2", "F1")
    # graph.add_edge("F1", "G2"), graph.add_edge("F2", "G1")

    graph.add_edge("A8", "B9"), graph.add_edge("A9", "B8")
    graph.add_edge("B8", "C9"), graph.add_edge("B9", "C8")
    graph.add_edge("C8", "D9"), graph.add_edge("C9", "D8")
    graph.add_edge("D8", "E9"), graph.add_edge("D9", "E8")
    # graph.add_edge("E8", "F9"), graph.add_edge("E9", "F8")
    # graph.add_edge("F8", "G9"), graph.add_edge("F9", "G8")



    graph.add_edge("A3", "A4"), graph.add_edge("A4", "A5"), graph.add_edge("A5", "A6"), graph.add_edge("A6", "A7")
    graph.add_edge("B3", "B4"), graph.add_edge("B4", "B5"), graph.add_edge("B5", "B6"), graph.add_edge("B6", "B7")
    graph.add_edge("C3", "C4"), graph.add_edge("C4", "C5"), graph.add_edge("C5", "C6"), graph.add_edge("C6", "C7")
    graph.add_edge("D3", "D4"), graph.add_edge("D4", "D5"), graph.add_edge("D5", "D6"), graph.add_edge("D6", "D7")
    graph.add_edge("E3", "E4"), graph.add_edge("E4", "E5"), graph.add_edge("E5", "E6"), graph.add_edge("E6", "E7")
    # graph.add_edge("F3", "F4"), graph.add_edge("F4", "F5"), graph.add_edge("F5", "F6"), graph.add_edge("F6", "F7")
    # graph.add_edge("G3", "G4"), graph.add_edge("G4", "G5"), graph.add_edge("G5", "G6"), graph.add_edge("G6", "G7")



    graph.add_edge("A1", "B1"), graph.add_edge("A2", "B2")
    graph.add_edge("B1", "C1"), graph.add_edge("B2", "C2")
    graph.add_edge("C1", "D1"), graph.add_edge("C2", "D2")
    graph.add_edge("D1", "E1"), graph.add_edge("D2", "E2")
    # graph.add_edge("E1", "F1"), graph.add_edge("E2", "F2")
    # graph.add_edge("F1", "G1"), graph.add_edge("F2", "G2")

    graph.add_edge("A9", "B9"), graph.add_edge("A8", "B8")
    graph.add_edge("B9", "C9"), graph.add_edge("B8", "C8")
    graph.add_edge("C9", "D9"), graph.add_edge("C8", "D8")
    graph.add_edge("D9", "E9"), graph.add_edge("D8", "E8")
    # graph.add_edge("E9", "F9"), graph.add_edge("E8", "F8")
    # graph.add_edge("F9", "G9"), graph.add_edge("F8", "G8")
    print(graph.graph)
    
    diem_chiem_dung = {
        ("A1","B2"): [("A2", "B1"), ("B1", "A2")],
        ("B2","A1"): [("A2", "B1"), ("B1", "A2")],
        ("A2","B1"): [("A1", "B2"), ("B1", "A2")],
        ("B1","A2"): [("A2", "B1"), ("B2", "A1")],

        ("B1","C2"): [("B2", "C1"), ("C1", "B2")],
        ("C2","B1"): [("B2", "C1"), ("C1", "B2")],
        ("B2","C1"): [("B1", "C2"), ("C1", "B2")],
        ("C1","B2"): [("B1", "C2"), ("C2", "B1")],

        ("C1","D2"): [("C2", "D1"), ("D1", "C2")],
        ("D2","C1"): [("C2", "D1"), ("D1", "C2")],
        ("C2","D1"): [("C1", "D2"), ("D1", "C2")],
        ("D1","C2"): [("C1", "D2"), ("D2", "C1")],

        ("D1","E2"): [("D2", "E1"), ("E1", "D2")],
        ("E2","D1"): [("D2", "E1"), ("E1", "D2")],
        ("D2","E1"): [("D1", "E2"), ("E1", "D2")],
        ("E1","D2"): [("D1", "E2"), ("E2", "D1")],

        ("A8","B9"): [("A9", "B8"), ("B8", "A9")],
        ("B9","A8"): [("A9", "B8"), ("B8", "A9")],
        ("A9","B8"): [("A8", "B9"), ("B9", "A8")],
        ("B8","A9"): [("A8", "B9"), ("B9", "A8")],

        ("B8","C9"): [("B9", "C8"), ("C8", "B9")],
        ("C9","B8"): [("B9", "C8"), ("C8", "B9")],
        ("B9","C8"): [("B8", "C9"), ("C9", "B8")],
        ("C8","B9"): [("B8", "C9"), ("C9", "B8")],

        ("C8","D9"): [("C9", "D8"), ("D8", "C9")],
        ("D9","C8"): [("C9", "D8"), ("D8", "C9")],
        ("C9","D8"): [("C8", "D9"), ("D9", "C8")],
        ("D8","C9"): [("C8", "D9"), ("D9", "C8")],

        ("D8","E9"): [("D9", "E8"), ("E8", "D9")],
        ("E9","D8"): [("D9", "E8"), ("E8", "D9")],
        ("D9","E8"): [("D8", "E9"), ("E9", "D8")],
        ("E8","D9"): [("D8", "E9"), ("E9", "D8")],


    }


    # 2. Khởi tạo Fleet Logic và Visualizer
    agv_ids = ["agv1", "agv2", "agv3"]
    fleet = FleetLogicRealTime(graph, agv_ids, diem_chiem_dung)
    visualizer = AGVVisualizer(graph, agv_ids)

    # 3. Dữ liệu cố định ban đầu
    current_telemetry = [
        {"agv_id": "agv1", "current_node": "C3", "status": "IDLE"},
        {"agv_id": "agv2", "current_node": "A1", "status": "IDLE"},
        {"agv_id": "agv3", "current_node": "D2", "status": "IDLE"},
    ]
    initial_jobs = [
        {"agv_id": "agv1", "goal": "D1"},
        {"agv_id": "agv2", "goal": "E2"},
        {"agv_id": "agv3", "goal": "B2"},
    ]

    print("--- BẮT ĐẦU ĐIỀU PHỐI VÒNG LẶP ---")
    
    running = True
    active_jobs = initial_jobs
    
    while running:
        input_data = {"telemetry": current_telemetry, "jobs": active_jobs}

        commands = fleet.run_cycle(input_data)

        new_telemetry = []
        for agv_id in agv_ids:
            cmd = commands.get(agv_id, {})
            current_agv_data = fleet.agvs[agv_id]
            
            # Mặc định lấy vị trí hiện tại
            current_node = current_agv_data["current_node"]
            
            if cmd.get("command") == "DI_CHUYEN":
                path = cmd.get("path", [])
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

    pygame.quit()