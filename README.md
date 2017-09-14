# magic-wormhole-transit-relay
Transit Relay server for Magic-Wormhole

This repo implements the Magic-Wormhole "Transit Relay", a server that helps
clients establish bulk-data transit connections even when both are behind NAT
boxes. Each side makes a TCP connection to this server and presents a
handshake. Two connections with identical handshakes are glued together,
allowing them to pretend they have a direct connection.
