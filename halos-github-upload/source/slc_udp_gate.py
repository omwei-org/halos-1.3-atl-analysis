#!/usr/bin/env python3
import argparse, hashlib, socket, time
from dataclasses import dataclass

PACKET_SIZE=64

@dataclass
class Authority:
    packet_sha256:str
    context_id:str
    epoch:int
    valid_until_ms:int
    target:str='ATL_CMD_RECEIVER'
    allow:bool=True

@dataclass
class Governance:
    context_id:str
    epoch:int
    route_permitted:bool=True
    safety_permitted:bool=True
    target:str='ATL_CMD_RECEIVER'


def decide(packet, auth, gov, now_ms=None):
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    digest=hashlib.sha256(packet).hexdigest()
    checks=[
        (len(packet)==PACKET_SIZE,'PACKET_SIZE'),
        (digest==auth.packet_sha256,'PAYLOAD_BINDING'),
        (auth.target==gov.target,'TARGET_MISMATCH'),
        (auth.context_id==gov.context_id,'CONTEXT_MISMATCH'),
        (now_ms<=auth.valid_until_ms,'AUTHORITY_EXPIRED'),
        (auth.epoch==gov.epoch,'EPOCH_MISMATCH'),
        (gov.route_permitted,'ROUTE_REVOKED'),
        (gov.safety_permitted,'SAFETY_NOT_PERMITTED'),
        (auth.allow,'AUTHORITY_DENIED'),
    ]
    for ok,reason in checks:
        if not ok: return False,reason,digest
    return True,'COMMIT_AUTHORIZED',digest


def addr(s):
    h,p=s.rsplit(':',1); return h,int(p)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--listen',default='127.0.0.1:12000')
    ap.add_argument('--forward',default='127.0.0.1:13000')
    ap.add_argument('--context',default='ATL:FORKLIFT:01')
    args=ap.parse_args()
    ls,fw=addr(args.listen),addr(args.forward)
    rx=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); rx.bind(ls)
    tx=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    gov=Governance(args.context,481)
    print(f'SLC gate {ls} -> {fw}; packet-preserving mode; epoch={gov.epoch}')
    while True:
        packet,peer=rx.recvfrom(4096)
        now=int(time.time()*1000)
        auth=Authority(hashlib.sha256(packet).hexdigest(),gov.context_id,gov.epoch,now+5000)
        allow,reason,digest=decide(packet,auth,gov,now)
        print(f'{peer} len={len(packet)} sha256={digest[:16]} decision={"ALLOW" if allow else "BLOCK"} reason={reason}')
        if allow: tx.sendto(packet,fw)

if __name__=='__main__': main()
