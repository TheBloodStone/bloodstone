import { registerPlugin } from '@capacitor/core';

export interface BloodstoneStratumPlugin {
  connect(options: { host: string; port: number }): Promise<{ connected: boolean }>;
  send(options: { line: string }): Promise<void>;
  disconnect(): Promise<void>;
}

const BloodstoneStratum = registerPlugin<BloodstoneStratumPlugin>('BloodstoneStratum');

export default BloodstoneStratum;