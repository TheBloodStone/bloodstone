import { registerPlugin } from '@capacitor/core';

export interface ChainMeshChunkMeta {
  chunkHash: string;
  sourceFile: string;
  fileOffset: number;
  size: number;
  savedAt: number;
}

export interface BloodstoneChainMeshPlugin {
  putChunk(options: {
    chunkHash: string;
    dataB64: string;
    sourceFile?: string;
    fileOffset?: number;
    size?: number;
  }): Promise<{ stored: boolean; chunkHash: string }>;
  getChunk(options: { chunkHash: string }): Promise<{
    chunkHash: string;
    dataB64: string;
    sourceFile: string;
    fileOffset: number;
    size: number;
  } | null>;
  listChunks(): Promise<{ chunks: ChainMeshChunkMeta[]; count: number }>;
  removeChunk(options: { chunkHash: string }): Promise<{ removed: boolean }>;
  getCapacity(): Promise<{
    maxChunks: number;
    usedChunks: number;
    maxBytes: number;
    usedBytes: number;
  }>;
  setMeshCapacity(options?: {
    mode?: 'pruned' | 'full' | 'mesh';
    maxChunks?: number;
  }): Promise<{ maxChunks: number; mode: string }>;
}

const BloodstoneChainMesh = registerPlugin<BloodstoneChainMeshPlugin>(
  'BloodstoneChainMesh',
);

export default BloodstoneChainMesh;