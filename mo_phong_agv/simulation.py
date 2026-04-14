# simulation.py
import pygame
import math

class AGVVisualizer:
    def __init__(self, graph_manager, agv_ids):
        pygame.init()
        self.graph_mgr = graph_manager
        self.screen = pygame.display.set_mode((1000, 800))
        pygame.display.set_caption("AGV Simulation - Controller Mode")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 12)
        
        # Lưu vị trí thực tế (x, y) của các AGV để vẽ
        self.visual_positions = {} 
        self.colors = {"agv1": (0, 120, 255), "agv2": (255, 100, 0), "agv3": (0, 200, 0)}

    def update_and_draw(self, current_telemetry, commands):
        """
        Nhận trạng thái hiện tại và lệnh, vẽ lên màn hình 
        và xử lý sự kiện Pygame để không bị treo cửa sổ.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False

        self.screen.fill((250, 250, 250))
        self._draw_map()

        for t in current_telemetry:
            agv_id = t["agv_id"]
            curr_node = t["current_node"]
            pos = self.graph_mgr.positions[curr_node]
            
            # Vẽ AGV tại node hiện tại
            color = self.colors.get(agv_id, (100, 100, 100))
            if t["status"] == "WAITING": color = (255, 0, 0)
            
            pygame.draw.rect(self.screen, color, (pos[0]-12, pos[1]-12, 24, 24))
            lbl = self.font.render(f"{agv_id}", True, (0,0,0))
            self.screen.blit(lbl, (pos[0]-15, pos[1]-30))

        pygame.display.flip()
        self.clock.tick(10) # Giới hạn tốc độ mô phỏng để dễ quan sát
        return True

    def _draw_map(self):
        for node, neighbors in self.graph_mgr.graph.items():
            p1 = self.graph_mgr.positions[node]
            for n in neighbors:
                p2 = self.graph_mgr.positions[n]
                pygame.draw.line(self.screen, (220, 220, 220), p1, p2, 1)
        for node, pos in self.graph_mgr.positions.items():
            pygame.draw.circle(self.screen, (200, 200, 200), pos, 3)