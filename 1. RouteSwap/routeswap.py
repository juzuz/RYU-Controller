

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib import hub


class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.monitor_thread = hub.spawn(self._monitor)
        self.datapath = []
        self.switchPath = True

    def PathSwitch(self):
        datapath1 = self.datapath[0]
        datapath2 = self.datapath[1]

        ofp1 = datapath1.ofproto
        ofp2 = datapath2.ofproto
        parser1 = datapath1.ofproto_parser
        parser2 = datapath2.ofproto_parser

        cookie = cookie_mask = 0
        table_id = 0
        idle_timeout = hard_timeout = 0
        priority = 10
        buffer_id_1 = ofp1.OFP_NO_BUFFER
        buffer_id_2 = ofp2.OFP_NO_BUFFER

        match1 = parser1.OFPMatch(in_port = 1)
        match2 = parser2.OFPMatch(in_port = 1)
        if self.switchPath:
            action1 = [parser1.OFPActionOutput(3)]
            action2 = [parser2.OFPActionOutput(3)]
        else:
            action1 = [parser1.OFPActionOutput(2)]
            action2 = [parser2.OFPActionOutput(2)]
        
        inst1 = [parser1.OFPInstructionActions(ofp1.OFPIT_APPLY_ACTIONS,action1)]
        inst2 = [parser2.OFPInstructionActions(ofp2.OFPIT_APPLY_ACTIONS,action2)]

        req1 = parser1.OFPFlowMod(datapath1, cookie, cookie_mask,
                                table_id, ofp1.OFPFC_ADD,
                                idle_timeout, hard_timeout,
                                priority, buffer_id_1,
                                ofp1.OFPP_ANY, ofp1.OFPG_ANY,
                                ofp1.OFPFF_SEND_FLOW_REM,
                                match1,inst1)

        req2 = parser2.OFPFlowMod(datapath2, cookie, cookie_mask,
                                table_id, ofp2.OFPFC_ADD,
                                idle_timeout, hard_timeout,
                                priority, buffer_id_2,
                                ofp1.OFPP_ANY, ofp2.OFPG_ANY,
                                ofp2.OFPFF_SEND_FLOW_REM,
                                match2,inst2)
        
        datapath1.send_msg(req1)
        datapath2.send_msg(req1)

        self.switchPath = not self.switchPath


    def _monitor(self):
        while True:
            hub.sleep(5)
            if self.datapath:
                self.PathSwitch()
            


                        
            

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # switch s1
        # Switch 1 is connected with host 1 through port 1
        # Switch 2 also has the same connectons. Therefore, they will be bundled
        if datapath.id == 1 or datapath.id == 2:
            self.datapath.append(datapath)

            actions = [parser.OFPActionOutput(2)]
            match = parser.OFPMatch(in_port=1)
            self.add_flow(datapath, 10, match, actions)

            actions = [parser.OFPActionOutput(1)]
            match = parser.OFPMatch(in_port=2)
            self.add_flow(datapath, 10, match, actions)

            actions = [parser.OFPActionOutput(1)]
            match = parser.OFPMatch(in_port=3)
            self.add_flow(datapath, 10, match, actions)

        #Switch 3 and 4 are bidirectional switches
        if datapath.id ==3 or datapath.id == 4:
            self.datapath.append(datapath)

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


