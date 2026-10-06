declare module 'react-native-sound' {
  type Completion = (success: boolean) => void;
  type LoadCompletion = (error?: Error | null) => void;
  export default class Sound {
    constructor(filename: string, basePath?: string, onLoad?: LoadCompletion);
    play(callback?: Completion): boolean;
    pause(callback?: () => void): void;
    release(): void;
    isPlaying(): boolean;
    getDuration(): number;
    getCurrentTime(callback: (seconds: number, isPlaying: boolean) => void): void;
    setCurrentTime(seconds: number): void;
    setSpeed(speed: number): void;
  }
}
