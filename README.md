# RYU Controller
Ryu provides software components with well-defined API's that make it easy for developers to create new network management and control applications. Ryu supports various protocols for managing network devices, such as OpenFlow, Netconf, OF-config, etc. About OpenFlow, Ryu supports fully 1.0, 1.2, 1.3, 1.4, 1.5 and Nicira Extensions. This Project will be an attempt to understand the usages of the Ryu controller under the guiding questions listed below:

## Set up the following network first:
>                s3
>
>              /     \
>
>     h1 -  s1         s2 - h2
>
>             \      /
>
>                s4

This is the topo file. I will set up this network through mininet.

![topo](/assets/topo.png)

## Write a RYU controller that switches paths (h1-s1-s3-s2-h2 or h1-s1-s4-s2-h2) between h1 and h2 every 5 seconds. 

The core code to accomplish this feat will be given and explained below.

From the ryu library we will be using the hub
> from ryu.lib import hub

From the hub library, we will use the spawn function to create a hub that will act as a thread that monitors the five seconds and then switches the paths.

I have decided to use a OFPFlowMod request to change the flows interchangeably.
But to correctly achieve the desired result, when s1 switches the flow path, s2 also needs to switch. The following code handles that problem while performing the flowmod.

![pathSwitch](/assets/pathSwitch.png)

When the packets get sent to the controller, it goes through each switch. The switches enter sequentially, aka dpid 1,2,3,4 for s1, s2, s3, s4.
Therefore, there is an append function that adds the datapath to the local variable self.datapath. This datapath will be used to send the flowmod request.

![swap](/assets/swap.png)

Using the Boolean switchPath, we can tell which flow was previously active. So we need to set the flow to the opposite flow.

![req](/assets/request.png)

After sending the FlowMod request to both switches s1 and s2, we need to negate the boolean so on the next loop, the flow will change to the original output port.

The last, but most important part is the switch feature handling.

![12](/assets/12.png)

Switches s1 and s2 can has two inflows from port 2 and 3. The outflow is initially set to go to port2(s3).
Switches s3 and s4 don’t need to worry about a thing and just needs to continue to direct the traffic bidirectionally.

### Results

![r1](/assets/r1.png)
![r2](/assets/r2.png)

From the timing from these two pictures, it is evident that at the 93 seconds to flow swapped from outport 3 to outport 2 at 98 seconds. 
Despite the switching of the paths, the h1 ping h2 command shows that there is no packet loss.

![p1](/assets/p1.png )

## Write a RYU controller that uses both paths to forward packets from h1 to h2.

To allow both paths to be used during transmission, I will be using the SELECT group type. Each of the SELECT group’s bucket has an assigned weight, and each packet that enters the group is sent to a single bucket. The bucket selection algorithm computes a hashing based on source port, source ip, dst port, dst ip to determine which bucket to use for routing. This causes a small problem while testing and its solution will be shared during the result section.

![load](/assets/load.png)
The crux of this task is the usage of the SELECT group. Switches S1 and S2 will output the inputs from the host to this group. The weight of the buckets are assigned to 50, therefore, ideally, half of the packets should be sent to bucket 1 and the other half to bucket 2.

![s1](/assets/s1.png)
![s2](/assets/s2.png)

As the results show, other than the initial 6 packets sent to s4 as soon as running mininet, all the others from the ping command are sent to the first bucket for both s1 and s2.

A simple solution was to run iperf with a -P flag, which stands for parallel. This starts multiple tcp/udp flows from different source port numbers. This can counter the same backet hashing problem on a single device.
The results are as follows:
In mininet run xterm h1 h2.
Setup h2 as the server and ping h2 from h1.


### Results
There is a slight problem when using the SELECT group. Because the bucket choice is based on the factors hash of the source port, source ip, dst port and the dst ip, the bucket that is chosen will always be the same. Because it is a hashing of these elements, the bucket chosen for the return will also be the same.

![par](/assets/par.png)

Although, this has not reached our ideal 50:50 distribution, but this is due to the bucket selection method. 

## Write a RYU controller that uses the first path (h1-s1-s3-s2-h2) for routing packets from h1 to h2 and uses the second path for backup. Specifically, when the first path experiences a link failure, the network should automatically switch to the second path without causing packet drop. 

The required backup functionality can be accomplished with the Fast Failover Group.
There is a slight difference in the code from the first task . First, the group type has to be changed to OFPGT_FF. The watch port for each bucket needs to be set to it’s own output port. The watch port is used to monitor the status of the output port. If the port is down, then the group will quickly switch over to the next available bucket. In our case s4.
![ffg](/assets/ffg.png)

Through the ovs-ofctl dump ports command, I can shut down a certain port. But as soon as we shut it down, there is a connection lost, and the packets are unable to traverse the netwokr.

The problem for the lost of connection is because port 2 of s1 is down, the ACK from h2 is also cut off.
Although s1 knows to send its packets to s4, s2 does not know the status of s3 switches port 1. 

The next code will be the implementation of telling s2 of the status of s1 and shutting the port down once s1 shuts down.

![portSwap](/assets/portSwap.png)

ofp_event has an event the monitors status changes of the ports. Using the @set_ev_cls, we will proc the handler whenever there is a status change.
During testing, I found out that when port 2 of s1 is shut down, the port 1 of s3 is also shut down. Therefore, the status of s3 port 1 can be used to monitor the status of s1 port 2.

I checked the reason for what proc’d the status change, and if it is s3 port 1 going down, a msg to shut down s2 port 2 will also be sent. And if it is the opposite, where s3 and port 1 is up, we tell s2 to go back live.

The tricky part of this method is getting the hw_addr for the OFPPortMod function.
In the case of a pre-known network, the hw_addr is constant, but in mininet the hw_addr changes each launch. To get this information I used the code below:

![conf_d](/assets/conf_d.png)

This gets the ports name and hw_addr while the controller installs the flows for each of the switches. Using this information, we can finish the code above.


### Results

For the testing, I will initiate a ping and shut down and reopen the ports.

After shutting down the s1 port 2.
This is the results of the ports of the three switches after running the command:

> sudo ovs-ofctl -o Openflow13 mod-port s1 2 down

![down](/assets/down.png)

This is the status of the ports after I reopen the down link

> sudo ovs-ofctl -o Openflow13 mod-port s1 2 up

![up](/assets/up.png)

As can be seen in the ping results, no packets were lost throughout the process.

![p3](/assets/p3.png)

