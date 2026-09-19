export {};
declare global {
  interface Window {
    huohuoDesktop?: {
      minimize(): Promise<void>;
      close(): Promise<void>;
      setPinned(value: boolean): Promise<boolean>;
    };
  }
}
