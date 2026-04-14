#Quản lý graph (map)

class GraphManager:
    def __init__(self):
        self.graph = {}          # {'A': ['B','C']}
        self.positions = {}      # {'A': (x,y)}

    def add_node(self, name, pos):
        self.positions[name] = pos
        if name not in self.graph:
            self.graph[name] = []

    def add_edge(self, n1, n2):
        if n2 not in self.graph[n1]:
            self.graph[n1].append(n2)
        if n1 not in self.graph[n2]:
            self.graph[n2].append(n1)
