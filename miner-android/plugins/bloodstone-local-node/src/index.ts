import { registerPlugin } from '@capacitor/core';

export interface LocalNodeStatus {
  running: boolean;
  mode: 'pruned' | 'full' | 'mesh' | 'consensus' | 'consensus-witness' | 'gateway' | 'stopped';
  lanIp: string;
  rpcPort: number;
  stratumPort: number;
  stratumPortYespower?: number;
  stratumPorts?: Record<string, number>;
  rpcUser: string;
  rpcPassword: string;
  rpcUrl: string;
  stratumHost: string;
  blockHeight: number;
  pruned: boolean;
  syncProgress?: number;
  chainBytes?: number;
  mdnsRegistered: boolean;
  networkWork?: Record<string, number | string | boolean>;
}

export interface NodeStorageInfo {
  freeBytes: number;
  prunedDatadirBytes: number;
  fullDatadirBytes: number;
  fullNodeMinFreeBytes: number;
  fullNodeEstimateBytes: number;
  canRunFullNode: boolean;
  recommendedMode: 'pruned' | 'full' | 'mesh';
}

export interface LocalWalletEntry {
  wallet: string;
  address: string;
  source?: string;
  createdAt?: number;
}

export interface LocalWalletCreateResult {
  ok: boolean;
  wallet: string;
  address: string;
  onDevice: boolean;
  encrypted?: boolean;
  note?: string;
}

export interface BloodstoneLocalNodePlugin {
  startLocalNode(options?: {
    upstreamUrl?: string;
    pruneMiB?: number;
    nodeMode?: 'pruned' | 'full' | 'mesh' | 'consensus' | 'consensus-witness';
  }): Promise<LocalNodeStatus>;
  stopLocalNode(): Promise<void>;
  getLocalNodeStatus(): Promise<LocalNodeStatus>;
  getNodeStorageInfo(): Promise<NodeStorageInfo>;
  getLanRpcUrl(): Promise<{ url: string; user: string; password: string }>;
  createLocalWallet(options: {
    passphrase: string;
    label?: string;
  }): Promise<LocalWalletCreateResult>;
  getNewLocalAddress(options: {
    wallet: string;
    label?: string;
    passphrase?: string;
  }): Promise<LocalWalletCreateResult>;
  listLocalWallets(): Promise<{
    onDevice: boolean;
    nodeRunning: boolean;
    entries: LocalWalletEntry[];
    count: number;
  }>;
}

const BloodstoneLocalNode = registerPlugin<BloodstoneLocalNodePlugin>(
  'BloodstoneLocalNode',
);

export default BloodstoneLocalNode;