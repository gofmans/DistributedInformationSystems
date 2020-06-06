from socket import socket
from socket import error
from socket import AF_INET
from socket import SOCK_STREAM
from socket import SOCK_DGRAM
from socket import SHUT_RDWR
from socket import SHUT_WR
from threading import Thread
from threading import Lock
from weights import get_new_weight


def router(my_name):
    # build router and first link state packet
    my_router = Routerr(my_name)
    my_router.current_link_state_packet = my_router.get_link_state_packet(my_router.update_round)




    # start listening
    threads = []
    threads.append(Thread(target=my_router.open_listening_UDP))  #open listening on UDP port
    threads.append(Thread(target=my_router.open_listening_TCP))  # open listening on TCP port
    for thread in threads:
        thread.start()


def get_params(name):
    file_name = 'input_router_' + str(name) + '.txt'
    params = open(file_name, 'r')
    lines = params.readlines()
    lines = [line.replace('\n', '') for line in lines]
    UDP_port, TCP_port, total_rout_num, first_neigh = lines[0:4]
    max_net_diam = lines[-1]
    l = lines[3:-2]
    fiths = [l[i:i + 5] for i in range(0, len(l), 5)]
    degree = len(fiths)
    neighbors = {}
    for i, n in enumerate(fiths):
        data = [n[1], int(n[2]), int(n[3]), int(n[4]), i]
        neighbors[int(n[0])] = data # [neighbor_id]: [ip, UDP, TCP, weight, serial_number]
    routing_table = {i + 1: [int(first_neigh), int(max_net_diam)] for i in range(int(total_rout_num))}  # [router_id]: [approx_distance, next_router_in_path]
    routing_table[name] = [0, None]
    return (int(name),int(UDP_port),int(TCP_port),int(total_rout_num),degree,neighbors,routing_table)


class Routerr:
    def __init__(self, name):
        params = get_params(name)
        self.name = params[0]
        self.UDP_port = params[1]
        self.TCP_port = params[2]
        self.net_size = params[3]
        self.degree = params[4]
        self.neighbors = params[5]  # [neighbor_id]: [n_name, ip, UDP, TCP,initial weight, serial_number]
        self.neighbors_lock = Lock()
        self.neighbors_keys = list(self.neighbors.keys())
        self.routing_table = params[6] # [router_id]: (approx_distance, next_router_in_path)
        self.routing_lock = Lock()
        self.routing_keys = list(self.routing_table.keys())
        self.update_round = 1
        self.round_lock = Lock()
        self.is_working = True
        self.UDP_output_file_name = 'UDP_output_router_' + str(self.name) + '.txt'
        self.UDP_output_lock = Lock()
        self.TCP_output_file_name = 'TCP_output_router_' + str(self.name) + '.txt'
        self.TCP_output_lock = Lock()
        self.current_link_state_packet = []
        self.packet_lock = Lock()
        self.routers_weights_round = {i: 0 for i in range(1, self.net_size + 1)}
        self.routers_weights_round[self.name] = 1 # i have my own data
        self.routers_weights_lock = Lock()
        self.did_not_received_all_packets = True
        self.all_packets_lock = Lock()
        self.adj_matrix = [[-1]*self.net_size for i in range(self.net_size)]
        self.adj_matrix_lock = Lock()


    def translate_message(self, message, action):
        if action == 'decode':
            decoded = message.decode()
            initial = [c for c in decoded.split(';')]
            update_round = int(initial[0])
            sender = int(initial[1])
            hoop_counter = int(initial[2])
            pairs = []
            rest = initial[3:-1]
            for i in range(0, len(rest), 2):
                pairs.append((int(rest[i]), int(rest[i + 1])))
            return update_round, sender, pairs, hoop_counter
        if action == 'encode':
            string_message = ''
            for c in message:
                string_message += str(c) + ';'
            return string_message


    def redecode_message(self,message):
        decoded = message.decode()
        original_message = [c for c in decoded.split(';')]
        original_message[2] = int(original_message[2]) - 1
        updated_message = ''
        for c in original_message:
            updated_message += str(c) + ';'
        return updated_message.encode()


    def send_UDP_message(self, message, target):
        with socket(AF_INET, SOCK_DGRAM) as s:
            try:
                s.sendto(message.encode(), target)
            except Exception as e:
                # print(e)
                pass



    def get_link_state_packet(self, update_round):
        # [source;neighbor_name; weight;neighbor_name;weight...]
        #ls_packet = [update_round, self.name]
        ls_packet = [update_round, self.name, self.net_size]
        with self.neighbors_lock:
            for k, val in self.neighbors.items():
                new_weight = get_new_weight(self.name, update_round, int(val[-1]), self.degree)
                val[-2] = new_weight if new_weight else val[-2]
                ls_packet.append(k) # neighbor name
                ls_packet.append(val[-2]) # neighbor weight
        return ls_packet


    def threaded_UDP_case_1(self, message):  # case 1: print routing table
        with self.UDP_output_lock:
            with open(self.UDP_output_file_name, 'a') as f:
                with self.routing_lock:
                    for k, val in self.routing_table.items():
                        f.write(str(val[0]) + ';' + str(val[1]) + '\n')


    def threaded_UDP_case_2(self, message):  # case 2: route given message
        message = message.decode()
        with self.UDP_output_lock:
            with open(self.UDP_output_file_name, 'a') as f:
                f.write(str(message) + '\n')
        temp_dest = message.split(';')[1]
        if str(temp_dest) == str(self.name):  # i'm the receiver, do nothing
            pass
        else:
            with socket(AF_INET, SOCK_DGRAM) as temp_s:
                with self.routing_lock:
                    next_in_path = self.routing_table[int(temp_dest)][1] # routing_table[router_id]: [approx_distance, next_router_in_path]
                with self.neighbors_lock:
                    next_in_path_udp_port = self.neighbors[next_in_path][1]
                temp_s.sendto(message.encode(), ('127.0.0.1', next_in_path_udp_port))


    def threaded_UDP_case_3(self, address):  #case 3: update routing table
        # 1 - send my link state packet to all neighbors
        with self.packet_lock:
            my_message = self.translate_message(self.current_link_state_packet, 'encode')
        self.spread_TCP_message(my_message, self.name)

        # 2 - get all link state packets from neighbors
        didnt_get_all_packets = self.check_for_all()
        while didnt_get_all_packets: #do it with function
            with self.all_packets_lock:
                didnt_get_all_packets = self.check_for_all()

        # 3 - run dijkstra
        my_graph = self.get_graph()
        new_routing_table = {}
        for r in self.routing_keys:
            if r == self.name: #no need to run dijkstra on myslf
                new_routing_table[r] = (0, None)
                continue
            path, distance = self.dijkstra(my_graph, self.name, r)
            new_routing_table[r] = (int(distance), path[1])

        # 4 - update routing table, reset all routing data relevant for this round
        with self.routing_lock:
            self.routing_table = new_routing_table

        # 5 - build link state packet for next round
        with self.round_lock:
            self.update_round += 1
            latest_round = self.update_round
        with self.packet_lock:
            self.current_link_state_packet = self.get_link_state_packet(latest_round)

        # reset control variables for next round
        with self.all_packets_lock:
            self.did_not_received_all_packets = True
        with self.routers_weights_lock:
            self.routers_weights_round[self.name] = latest_round  # i have my own data
        with self.adj_matrix_lock:
            self.adj_matrix = [[-1] * self.net_size for i in range(self.net_size)]

        # 6 - return FINISHED message to sender ?, who is the sender?
        self.send_UDP_message('FINISHED', address)


    def open_listening_UDP(self):
        # open listening on UDP port
        with socket(AF_INET, SOCK_DGRAM) as UDP_sock:  # UDP
            UDP_sock.bind(('127.0.0.1', self.UDP_port))
            while True:
                if not self.is_working:
                    return
                else:
                    message, addr = UDP_sock.recvfrom(4096)
                    case_type = message.decode()
                    if case_type.startswith('PRINT'):                           # case 1
                        action = Thread(target=self.threaded_UDP_case_1, args=(message,))
                    elif case_type.startswith('ROUTE'):                         # case 2
                        action = Thread(target=self.threaded_UDP_case_2, args=(message,))
                    elif case_type.startswith('UPDATE'):                        # case 3
                        action = Thread(target=self.threaded_UDP_case_3, args=(addr,))
                    elif case_type.startswith('SHUT'):                          # case 4
                        self.is_working = False
                        with socket(AF_INET, SOCK_DGRAM) as UDP_killer:
                            try:
                                UDP_killer.sendto(''.encode(), ('127.0.0.1', self.UDP_port))
                            except Exception as e:
                                #print(e)
                                pass
                        with socket(AF_INET, SOCK_STREAM) as TCP_killer:
                            try:
                                TCP_killer.connect(('127.0.0.1', self.TCP_port))
                                TCP_killer.sendall(''.encode())
                            except Exception as e:
                                #print(e)
                                pass
                            return
                    action.start()


    def open_listening_TCP(self):
         with socket(AF_INET, SOCK_STREAM) as TCP_sock: #TCP
            TCP_sock.bind(('127.0.0.1', self.TCP_port))
            TCP_sock.listen(99999999)  #backlog ?
            while True:
                if not self.is_working:
                    return
                else:
                    conn, addr = TCP_sock.accept()
                    with conn:
                        if not self.is_working:
                            return
                        message = conn.recv(4096)
                        action = Thread(target=self.handle_TCP_message, args = (message,))
                        action.start()


    def send_TCP_message(self, message, target_address, target_name):
        with self.TCP_output_lock:
            with open(self.TCP_output_file_name, 'a') as f:
                f.write('UPDATE;' + str(self.name) +';' + str(target_name) +'\n')
        with socket(AF_INET, SOCK_STREAM) as temp_s:
            try:
                temp_s.connect(target_address)
                temp_s.sendall(message.encode())
                temp_s.recv(4096)
            except Exception as e:
                pass
                #print("Error on router {}, while sending to {}. \n{}".format(self.name, target_name, e))


    def spread_TCP_message(self, message, source):
        threads = []
        for neighbor in self.neighbors_keys:  # send message to all neighbors
            if neighbor == source:
                continue # no need to send message to sender
            with self.neighbors_lock:
                temp_address = ('127.0.0.1', self.neighbors[neighbor][2])
                neighbor_name = neighbor
            self.send_TCP_message(message, temp_address, neighbor_name)
        #     threads.append(Thread(target=self.send_TCP_message, args =(message, temp_address, neighbor_name)))
        # for thread in threads:
        #     thread.start()


    def handle_TCP_message(self, message):
        packet_round, sender, pairs, hoop_counter = self.translate_message(message, 'decode')
        with self.routers_weights_lock:
            latest_known_round = self.routers_weights_round[sender]
        if sender == self.name or packet_round <= latest_known_round or hoop_counter < 0: # i got older packet from him, ignore
            return

        with self.round_lock:
            my_update_round = self.update_round
        for pair in pairs: # pair = (neighbor, weight)
            with self.adj_matrix_lock:
                self.adj_matrix[sender - 1][pair[0] - 1] = pair[1] #update adj matrix
            with self.routers_weights_lock:
                self.routers_weights_round[sender] = packet_round # now we got the relevant weights the newest update round
        with self.routers_weights_lock:
            if all(val == my_update_round for val in self.routers_weights_round.values()): #got all values for this update round
                with self.all_packets_lock:
                    self.did_not_received_all_packets = False
        updated_message = self.redecode_message(message)
        self.spread_TCP_message(message.decode(), self.name)


    def check_for_all(self):
        return self.did_not_received_all_packets


    def get_graph(self):
        ''' graph = {'s': {'a': 2, 'b': 1},
                 'a': {'s': 3, 'b': 4, 'c': 8},
                 'b': {'s': 4, 'a': 2, 'd': 2},
                 'c': {'a': 2, 'd': 7, 't': 4},
                 'd': {'b': 1, 'c': 99, 't': 5},
                 't': {'c': 3, 'd': 5}} '''
        temp_graph = {}
        for i in range(1, self.net_size + 1): #for all routers in the network
            temp_row = {}  # temp dictionary to store all outgoing edges
            if i == self.name: #get my new weights from current link state packet
                with self.packet_lock:
                    workable_list = self.current_link_state_packet[3::]
                for k in range(0, len(workable_list), 2): # pair: (neighbor_name, weight)
                    pair = (workable_list[k], workable_list[k + 1])
                    temp_row[pair[0]] = pair[1]
            else:
                for j in range(1, self.net_size + 1): #for all other routers in the network
                    if i == j:# no need to update weight of edge to myself
                        continue
                    with self.adj_matrix_lock:
                        if self.adj_matrix[i - 1][j - 1] != -1: # there is an edge between them
                            temp_row[j] = self.adj_matrix[i - 1][j - 1] # add to dictionary
            temp_graph[i] = temp_row
        return temp_graph


    def dijkstra(self, graph, source, destination):
        # initialize helpful variables
        unvisited = list(graph.keys())
        shortest_paths_info = dict()
        for v in unvisited:
            shortest_paths_info[v] = [[], float('inf')]

        # go over all unvisited nodes
        shortest_paths_info[source][1] = 0.0
        while len(unvisited) > 0:
            min_dis, current_node = min([(shortest_paths_info[n][1], n) for n in unvisited])
            shortest_paths_info[current_node][0].append(current_node)
            if current_node == destination:
                return shortest_paths_info[destination][0], shortest_paths_info[destination][1]

            # go over all neighbors
            for n, d in graph[current_node].items():
                if n in unvisited:
                    current_distance = min_dis + d
                    if current_distance < shortest_paths_info[n][1]:
                        shortest_paths_info[n][1] = current_distance
                        shortest_paths_info[n][0] = shortest_paths_info[current_node][0][:]
            unvisited.remove(current_node)
        return shortest_paths_info #not really going to use this line
