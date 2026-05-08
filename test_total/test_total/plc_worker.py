# plc_worker.py
import time
import threading
from collections import deque
from PyQt5.QtCore import QObject, pyqtSignal
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder
from pymodbus.constants import Endian
from config import MOTOR_LIST, OFFSETS, X1_DISCRETE_INPUT_ADDR

class PlcWorker(QObject):
    data_updated = pyqtSignal(dict, dict)      
    connection_status = pyqtSignal(bool, str)  
    
    def __init__(self, ip, port=502):
        super().__init__()
        self.ip = ip
        self.port = port
        self.client = None
        self.running = False
        self.write_queue = deque()
        self._lock = threading.Lock()

    def connect_plc(self):
        if self.running: return
        try:
            self.client = ModbusTcpClient(self.ip, port=self.port)
            if self.client.connect():
                self.running = True
                self.connection_status.emit(True, "连接成功")
                threading.Thread(target=self._polling_loop, daemon=True).start()
            else:
                self.connection_status.emit(False, "连接失败：握手被拒绝")
        except Exception as e:
            self.connection_status.emit(False, f"连接异常: {str(e)}")

    def disconnect_plc(self):
        self.running = False
        if self.client:
            self.client.close()
        self.connection_status.emit(False, "已断开")

    def add_write_task(self, task_type, address, value, bit=None):
        with self._lock:
            self.write_queue.append({'type': task_type, 'addr': address, 'val': value, 'bit': bit})

    def _polling_loop(self):
        last_success_time = time.time()
        while self.running:
            while self.write_queue:
                task = None
                with self._lock:
                    if self.write_queue: task = self.write_queue.popleft()
                if task:
                    try: self._process_write(task)
                    except Exception as e: print(f"Write Failed: {e}")

            try:
                g_rr = self.client.read_holding_registers(0, 10)
                if g_rr.isError(): raise Exception("Global Read Error")
                
                full_registers = {}
                ranges = [(100, 100), (200, 100), (300, 100), (400, 85)]
                for start, count in ranges:
                    rr = self.client.read_holding_registers(start, count)
                    if not rr.isError():
                        for i, val in enumerate(rr.registers): full_registers[start + i] = val
                
                # 读取 X1 传感器离散输入
                x1_status = False
                try:
                    x1_rr = self.client.read_discrete_inputs(X1_DISCRETE_INPUT_ADDR, 1)
                    if not x1_rr.isError():
                        x1_status = x1_rr.bits[0]
                except Exception:
                    pass
                
                last_success_time = time.time()
                self._parse_and_emit(g_rr.registers, full_registers, x1_status)
                
            except Exception:
                if time.time() - last_success_time > 5.0:
                    self.connection_status.emit(False, "连接超时 (5s无响应)")
                    self.running = False
                    break
            time.sleep(0.1)

    def _process_write(self, task):
        if task['type'] == 'coil':
            self.client.write_coil(task['addr'], task['val'])
        elif task['type'] == 'float':
            builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
            builder.add_32bit_float(float(task['val']))
            payload = builder.build()
            self.client.write_registers(task['addr'], payload, skip_encode=True)
        elif task['type'] == 'int16':
            self.client.write_register(task['addr'], int(task['val']))
        elif task['type'] == 'register_bit':
            rr = self.client.read_holding_registers(task['addr'], 1)
            if not rr.isError():
                current_val = rr.registers[0]
                bit_mask = 1 << task['bit']
                new_val = current_val | bit_mask if task['val'] else current_val & (~bit_mask)
                self.client.write_register(task['addr'], int(new_val))

    def _parse_and_emit(self, global_regs, motor_regs, x1_status=False):
        parsed_motors = {}
        parsed_global = {}
        d1_val = global_regs[1]
        parsed_global['sync_done'] = ((d1_val >> 0) & 1) and ((d1_val >> 4) & 1)
        parsed_global['x1_status'] = x1_status
        
        for motor in MOTOR_LIST:
            base = motor['base']
            m_data = {}
            def get_float(addr):
                r1, r2 = motor_regs.get(addr, 0), motor_regs.get(addr + 1, 0)
                decoder = BinaryPayloadDecoder.fromRegisters([r1, r2], byteorder=Endian.Big, wordorder=Endian.Little)
                return decoder.decode_32bit_float()
            
            m_data['act_pos'] = get_float(base + OFFSETS['act_pos'])
            m_data['act_vel'] = get_float(base + OFFSETS['act_vel'])
            m_data['act_tor'] = get_float(base + OFFSETS['act_tor'])
            status_word = motor_regs.get(base + OFFSETS['status_word_offset'], 0)
            m_data['is_powered'] = (status_word >> OFFSETS['is_powered_bit']) & 1
            
            parsed_motors[motor['name']] = m_data
            
        self.data_updated.emit(parsed_motors, parsed_global)