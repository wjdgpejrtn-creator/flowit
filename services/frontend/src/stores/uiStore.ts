import { create } from 'zustand';

export type UIState = 'normal' | 'loading' | 'error' | 'empty';

interface UIStoreState {
  state: UIState;
  setState: (state: UIState) => void;
}

export const useUIStore = create<UIStoreState>((set) => ({
  state: 'normal',
  setState: (state) => set({ state }),
}));
