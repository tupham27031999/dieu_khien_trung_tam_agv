# core/fleet_logic_thuc_te.py

import heapq
import random
import json

class FleetLogicRealTime:
    """
    Lớp logic điều khiển đội xe (fleet) được thiết kế cho môi trường thực tế.
    Hoạt động theo cơ chế hướng sự kiện:
    1. Nhận dữ liệu trạng thái (telemetry) từ AGV.
    2. Xử lý logic (tìm đường, tránh va chạm).
    3. Xuất ra lệnh điều khiển cho AGV.
    """

    def __init__(self, graph_manager, initial_agv_ids):
        self.graph = graph_manager.graph
        self.positions = graph_manager.positions
        self.agvs = {}

        # Khởi tạo trạng thái ban đầu cho các AGV, giả định chúng chưa có vị trí
        for agv_id in initial_agv_ids:
            self.agvs[agv_id] = {
                "agv_id": agv_id,
                "current_node": None,  # Sẽ được cập nhật khi nhận telemetry đầu tiên
                "goal": None,
                "path": [],
                "status": "UNKNOWN",  # Trạng thái ban đầu: UNKNOWN, IDLE, MOVING, ERROR
                # "battery": 100,
                "obstacle_detected": False,
            }

    # ==========================================================
    # INPUT: Cập nhật thông tin từ một AGV thực tế
    # ==========================================================
    def update_agv_telemetry(self, telemetry_data):
        """
        Hàm này là điểm đầu vào. Nó nhận một gói tin từ một AGV
        và cập nhật trạng thái nội bộ của fleet manager.
        """
        agv_id = telemetry_data.get("agv_id")
        if not agv_id or agv_id not in self.agvs:
            print(f"[LỖI] Nhận được telemetry cho AGV không xác định: {agv_id}")
            return

        agv_state = self.agvs[agv_id]
        
        # Cập nhật các thông số cơ bản
        agv_state["current_node"] = telemetry_data.get("current_node", agv_state["current_node"])
        agv_state["status"] = telemetry_data.get("status", agv_state["status"])
        # agv_state["battery"] = telemetry_data.get("battery", agv_state["battery"])
        agv_state["obstacle_detected"] = telemetry_data.get("obstacle_detected", False)

        # Logic quan trọng: Nếu AGV báo đã hoàn thành nhiệm vụ (IDLE) và đang ở đích,
        # ta xóa path cũ để nó sẵn sàng nhận nhiệm vụ mới.
        if agv_state["status"] == "IDLE" and agv_state["path"] and agv_state["current_node"] == agv_state["path"][-1]:
            print(f"[{agv_id}] đã xác nhận hoàn thành nhiệm vụ tại {agv_state['current_node']}.")
            agv_state["path"] = []
            agv_state["goal"] = None

    # ==========================================================
    # OUTPUT: Xử lý logic và tạo lệnh điều khiển
    # ==========================================================
    def process_and_generate_commands(self):
        """
        Chỉ xử lý di chuyển và tránh va chạm.
        Không tự sinh nhiệm vụ.
        """

        commands_to_send = {}

        reserved_nodes = self._get_all_reserved_nodes()
        # print(reserved_nodes) # {'A1': 'agv1', 'B1': 'agv1', 'C2': 'agv2'}

        for agv_id, agv in self.agvs.items():

            # Nếu chưa có path hoặc chưa có vị trí → bỏ qua
            if not agv["path"] or not agv["current_node"]:
                continue

            # Nếu đã tới đích → không cần lệnh
            if agv["current_node"] == agv["path"][-1]:
                continue

            # Xác định node tiếp theo
            try:
                current_index = agv["path"].index(agv["current_node"])
                next_node = agv["path"][current_index + 1]
            except (ValueError, IndexError):
                print(f"[{agv_id}] LOST PATH")
                agv["path"] = []
                agv["goal"] = None
                commands_to_send[agv_id] = {
                    "command": "STOP",
                    "reason": "LOST_PATH"
                }
                continue

            # =========================
            # KIỂM TRA AN TOÀN 
            # nếu có vật cản, Nếu node tiếp theo đang bị AGV khác giữ thì không đi
            # AGV có ID nhỏ hơn được ưu tiên
            # AGV ID lớn hơn phải nhường
            # =========================

            is_safe = True
            reason = ""

            # 1️⃣ Vật cản vật lý
            if agv["obstacle_detected"]:
                is_safe = False
                reason = "PHYSICAL_OBSTACLE"

            # 2️⃣ Node bị AGV khác giữ
            if next_node in reserved_nodes and reserved_nodes[next_node] != agv_id:
                blocker_id = reserved_nodes[next_node]

                # Ưu tiên AGV có ID nhỏ hơn
                if agv_id > blocker_id:
                    is_safe = False
                    reason = f"YIELD_TO_{blocker_id}"

            # =========================
            # TẠO LỆNH
            # =========================

            if is_safe:
                remaining_path = agv["path"][current_index:]
                commands_to_send[agv_id] = {
                    "command": "MOVE",
                    "path": remaining_path
                }
            else:
                commands_to_send[agv_id] = {
                    "command": "WAIT",
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
        reserved = {}
        # Sắp xếp để đảm bảo AGV có ID nhỏ hơn được ưu tiên khi chiếm node
        sorted_agvs = sorted(self.agvs.items())

        for agv_id, agv in sorted_agvs:
            if not agv["current_node"]: continue
            
            # Node hiện tại luôn bị chiếm
            if agv["current_node"] not in reserved:
                reserved[agv["current_node"]] = agv_id
            
            # Node tiếp theo cũng được "đặt trước"
            if agv["path"]:
                try:
                    current_path_index = agv["path"].index(agv["current_node"])
                    if current_path_index + 1 < len(agv["path"]):
                        next_node = agv["path"][current_path_index + 1]
                        if next_node not in reserved:
                           reserved[next_node] = agv_id
                except (ValueError, IndexError):
                    pass
        return reserved

    def assign_job(self, agv_id, goal_node):
        """
        Nhận job từ hệ thống trung tâm.
        """
        if agv_id not in self.agvs:
            print(f"[LỖI] AGV {agv_id} không tồn tại.")
            return False

        agv = self.agvs[agv_id]

        if not agv["current_node"]:
            print(f"[{agv_id}] chưa có vị trí, chưa thể gán nhiệm vụ.")
            return False

        obstacles = self._get_static_obstacles(exclude_agv_id=agv_id)
        path = self._a_star(agv["current_node"], goal_node, obstacles)

        if path and len(path) > 1:
            agv["goal"] = goal_node
            agv["path"] = path
            print(f"[{agv_id}] nhận nhiệm vụ: {agv['current_node']} -> {goal_node}")
            return True

        print(f"[{agv_id}] không tìm được đường tới {goal_node}")
        return False
    
    def run_cycle(self, input_data):
        """
        Chạy 1 vòng xử lý hoàn chỉnh:
        - Nhận telemetry
        - Nhận job từ trung tâm
        - Sinh lệnh điều khiển
        """

        # 1️⃣ Cập nhật telemetry
        for packet in input_data.get("telemetry", []):
            self.update_agv_telemetry(packet)

        # 2️⃣ Nhận job từ trung tâm
        for job in input_data.get("jobs", []):
            agv_id = job.get("agv_id")
            goal = job.get("goal")
            if agv_id and goal:
                self.assign_job(agv_id, goal)

        # 3️⃣ Sinh lệnh điều khiển
        commands = self.process_and_generate_commands()

        return commands

# ==========================================================
# PHẦN CHẠY THỬ NGHIỆM (DEMO CHO 1 VÒNG LẶP)
# ==========================================================
if __name__ == "__main__":

    from graph_manager import GraphManager
    import json

    mock_graph = GraphManager()
    mock_graph.add_node("A1", (100, 100)); mock_graph.add_node("B1", (100, 200)); mock_graph.add_node("C1", (100, 300))
    mock_graph.add_node("A2", (200, 100)); mock_graph.add_node("B2", (200, 200)); mock_graph.add_node("C2", (200, 300))
    mock_graph.add_edge("A1", "B1"); mock_graph.add_edge("B1", "C1")
    mock_graph.add_edge("A2", "B2"); mock_graph.add_edge("B2", "C2")
    mock_graph.add_edge("A1", "A2"); mock_graph.add_edge("B1", "B2"); mock_graph.add_edge("C1", "C2")

    fleet = FleetLogicRealTime(mock_graph, ["agv1", "agv2"])

    # ====== INPUT TỪ HỆ THỐNG ======
    input_data = {
        "telemetry": [
            {
                "agv_id": "agv1",
                "current_node": "A1",
                "status": "IDLE",
                "obstacle_detected": False
            },
            {
                "agv_id": "agv2",
                "current_node": "C2",
                "status": "IDLE",
                "obstacle_detected": False
            }
        ],
        "jobs": [
            {
                "agv_id": "agv1",
                "goal": "C1"
            },
            {
                "agv_id": "agv2",
                "goal": "A1"
            }
        ]
    }

    print("="*30)
    print("BẮT ĐẦU CHU KỲ")
    print("="*30)

    output_commands = fleet.run_cycle(input_data)

    print("\nOUTPUT COMMANDS:")
    print(json.dumps(output_commands, indent=2))

    print("="*30)