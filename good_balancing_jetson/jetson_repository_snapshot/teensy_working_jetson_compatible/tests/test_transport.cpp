#include <cassert>
#include <vector>
#include "ethernet_transport.h"
using namespace pendulum_net;
std::vector<std::string> commands;int stops=0;
void command(char *p){commands.push_back(p);}
void lost(){++stops;}
std::shared_ptr<State> connect(bool allowed=true){auto s=std::make_shared<State>();pending.s=s;poll(allowed,command,lost);return s;}
int main(){
 assert(begin());auto denied=connect(false);assert(!active&&!denied->connected);
 auto peer=connect();assert(active);auto second=connect();assert(!second->connected&&active);
 peer->rx="pi";poll(false,command,lost);assert(commands.empty());
 peer->rx="ng\nstop\n";poll(false,command,lost);assert(commands.size()==1&&commands[0]=="ping");
 poll(false,command,lost);assert(commands.size()==2&&commands[1]=="stop");
 peer->rx=std::string(110,'x')+"\nping\n";
 poll(false,command,lost);poll(false,command,lost);assert(commands.size()==2);
 poll(false,command,lost);assert(commands.size()==3);
 enqueue("test\n",5);peer->space=0;serviceTx();assert(peer->tx.empty());
 peer->space=8192;serviceTx();assert(peer->tx=="test\n");
 auto before=dropped;enqueue(std::string(8192,'x').c_str(),8192);assert(dropped==before+1);
 peer->rx="auto\n";Ethernet.link=false;poll(false,command,lost);
 assert(stops==1&&!active&&commands.size()==3&&head==tail);
}
