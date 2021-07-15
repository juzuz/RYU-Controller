

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types


class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.ports = []



    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # switch s1
        # Switch 1 is connected with host 1 through port 1
        # Switch 2 also has the same connectons. Therefore, they will be bundled
        if datapath.id == 1 or datapath.id == 2:
            # Send a Group mod to send anything coming from port 1 to port2(Switch 3) and port3(Switch4)
            self.send_group_req(datapath)
            actions = [parser.OFPActionGroup(group_id=100)]
            match = parser.OFPMatch(in_port=1)
            self.add_flow(datapath, 10, match, actions)

            # Anything that comes in from port2 and 3 is sent to port 1
            actions = [parser.OFPActionOutput(1)]
            match = parser.OFPMatch(in_port=2)
            self.add_flow(datapath, 10, match, actions)

            actions = [parser.OFPActionOutput(1)]
            match = parser.OFPMatch(in_port=3)
            self.add_flow(datapath, 10, match, actions)

        # if datapath.id == 2:
        #     # Send a Group mod to send anything coming from port 1 to port2(Switch 3) and port3(Switch4)
        #     self.send_group_req(datapath)
        #     actions = [parser.OFPActionGroup(group_id=100)]
        #     match = parser.OFPMatch(in_port=1)
        #     self.add_flow(datapath, 10, match, actions)

        #     # Anything that comes in from port2 and 3 is sent to port 1
        #     actions = [parser.OFPActionOutput(1)]
        #     match = parser.OFPMatch(in_port=2)
        #     self.add_flow(datapath, 10, match, actions)

        #     actions = [parser.OFPActionOutput(1)]
        #     match = parser.OFPMatch(in_port=3)
        #     self.add_flow(datapath, 10, match, actions)

        #Switch 3 and 4 are bidirectional switches
        if datapath.id ==3 or datapath.id == 4:
            actions = [parser.OFPActionOutput(2)]
            match = parser.OFPMatch(in_port=1)
            self.add_flow(datapath, 10, match, actions)

            actions = [parser.OFPActionOutput(1)]
            match = parser.OFPMatch(in_port=2)
            self.add_flow(datapath, 10, match, actions)


    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, CONFIG_DISPATCHER)
    def port_desc_stats_reply_handler(self,ev):
        for p in ev.msg.body:
            self.ports.append('{} {}'.format(p.name.decode('utf-8'),p.hw_addr))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # If you hit this you might want to increase
        # the "miss_send_length" of your switch
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            # ignore lldp packet
            return
        dst = eth.dst
        src = eth.src

        dpid = datapath.id
     

        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            # verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)


    # A GroupMod Request sent. Install the group to s1 and s2.
    def send_group_req(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # This is our flow balance percentages

        watch_port1 = 2
        watch_port2 = 3
        watch_group = 0

        weight = 0

        actions1 = [parser.OFPActionOutput(2)]
        actions2 = [parser.OFPActionOutput(3)]
        buckets = [parser.OFPBucket(weight, watch_port1, watch_group, actions=actions1),
                   parser.OFPBucket(weight, watch_port2, watch_group, actions=actions2)]
        
        req = parser.OFPGroupMod(datapath, ofproto.OFPGC_ADD,
                                 ofproto.OFPGT_FF, 100, buckets)
        datapath.send_msg(req)


    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofp = datapath.ofproto
        reason = msg.reason
        port_no = msg.desc.port_no
        parser = datapath.ofproto_parser
        hw_addr = ""
        self.logger.info(" MODIFIED {}  {}".format(dpid, port_no))
        if reason == ofp.OFPPR_MODIFY:
            port_down = msg.desc.state & ofp.OFPPS_LINK_DOWN
            if dpid == 3 and port_no == 1 and port_down:
                for port_name in self.ports:
                    if port_name[:7] == 's3-eth2':
                        hw_addr = port_name[8:]
                msg = parser.OFPPortMod(datapath,2,hw_addr,ofp.OFPPC_PORT_DOWN,ofp.OFPPC_PORT_DOWN, 0 )
                datapath.send_msg(msg)
            if dpid == 3 and port_no == 1 and not port_down:
                for port_name in self.ports:
                    if port_name[:7] == 's3-eth2':
                        hw_addr = port_name[8:]
                msg = parser.OFPPortMod(datapath,2,hw_addr,0,ofp.OFPPC_PORT_DOWN,0 )
                datapath.send_msg(msg)
        
        