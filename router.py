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


class Routerr:
    def __init__(self, name):
        self.name = int(name)
        file_name = 'input_router_' + str(name) + '.txt'
        params = open(file_name, 'r')
        lines = params.readlines()
        lines = [line.replace('\n', '') for line in lines]
        UDP_port, TCP_port, total_rout_num, first_neigh = lines[0:4]
        max_net_diam = lines[-1]
        l = lines[3:-2]
        fiths = [l[i:i + 5] for i in range(0, len(l), 5)]
        self.degree = len(fiths)
        self.neighbors = {n[0]: n[1::] + [i + 1] for i, n in enumerate(fiths)}   # [neighbor_id]: [n_name, ip, UDP, TCP, weight, serial_number]
        self.routing_table = {i + 1: [first_neigh, int(max_net_diam)] for i in range(int(total_rout_num))}  # [router_id]: [approx_distance, next_router_in_path]
        self.routing_table[name] = [None, 0]
        self.UDP_port = int(UDP_port)
        self.TCP_port = int(TCP_port)
        self.update_round = 1


    def get_link_state_packet(self):
        n_weights = {}
        for k, val in self.neighbors.items():
            new_weight = get_new_weight(self.name, self.update_round, val[-1], self.degree)
            val[-2] = new_weight if new_weight else val[-2]
            n_weights[k] = val[-2]
        return n_weights, self.update_round


def threaded_UDP(c, my_lock, my_router):
    f_name = 'test_UDP_output_router_' + str(my_router.name) + '.txt'
    while True:
        # data received from client
        message = c.recv(4096)
        message = message.decode() #translate back to string
        if message.startswith('PRINT'):                                   #case 1
            with open(f_name, 'a') as f:
                for k, val in my_router.routing_table.items():
                    f.write(str(val[0]) + ';' + str(val[1]) + '\n')
            my_lock.release()  # at end of action
            c.close()
        elif message.startswith('ROUTE'):                                 #case 2
            with open(f_name, 'a') as f:
                f.write(str(message) + '\n')
            temp_dest = message.split(';')[1]
            if str(temp_dest) == str(my_router.name): # i'm the receiver, do nothing
                pass
            else:
                sock_udp = socket(AF_INET, SOCK_DGRAM)
                temp_port = my_router[my_router.routing_table[temp_dest][1]][2]
                sock_udp.sendto(message.encode(), ('127.0.0.1', temp_port))
                data = sock_udp.recv(4096)
                sock_udp.close()
                if data.decode() != 'FINISHED':
                    print('Neighbor In IP: 127.0.0.1 and port: ', temp_port , 'failed')
            my_lock.release()  # at end of action
            c.close()
        elif message.startswith('UPDATE'):                                #case 3
            print('Update tables here')
            my_lock.release()  # at end of action
            c.close()
            pass

        elif message.startswith('SHUT'):                                  #case 4
            print('Stop listening of both ports here')
            my_lock.release()  # at end of action
            c.close()


#
# def threaded_TCP(c, my_lock, my_router):
#     while True:
#         # data received from client
#         messege = c.recv(4096)
#
#         my_lock.release()  # at end of action
#     c.close()



def router(my_name):
    # construct router object
    my_router = Routerr(my_name)

    # generate link state packet before listening on ports
    adjs, round = my_router.get_link_state_packet()

    my_lock = Lock()  # our locking method

    #open listening on UDP port
    UDP_sock = socket(AF_INET, SOCK_DGRAM)  # UDP
    UDP_sock.bind(('127.0.0.1', my_router.UDP_port))
    UDP_sock.listen(999)  #backlog ?
    while True:
        c, addr = UDP_sock.accept()
        my_lock.acquire()
        Thread(target=threaded_UDP, args=(c, my_lock, my_router))
    UDP_sock.close()


    # open listening on TCP port
    TCP_sock = socket(AF_INET, SOCK_STREAM) #TCP
    TCP_sock.bind(('127.0.0.1', my_router.TCP_port))
    TCP_sock.listen(999)  #backlog ?
    while True:
        c, addr = TCP_sock.accept()
        my_lock.acquire()
        Thread(target=threaded_TCP, args=(c, my_lock, my_router))
    TCP_sock.close()