import { registerPlugin } from '@capacitor/core';

export interface FleetIdentity {
  deviceId: string;
  model: string;
  manufacturer: string;
  platform: string;
  role: string;
}

export interface BloodstoneDevicePoolPlugin {
  getIdentity(): Promise<FleetIdentity>;
  startFleetNode(options?: {
    address?: string;
    algo?: string;
  }): Promise<{ running: boolean; role: string }>;
  stopFleetNode(): Promise<void>;
  getFleetStatus(): Promise<{ running: boolean; role: string }>;
}

const BloodstoneDevicePool = registerPlugin<BloodstoneDevicePoolPlugin>(
  'BloodstoneDevicePool',
);

export default BloodstoneDevicePool;