import { Config } from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
Config.setPixelFormat('yuv420p');
Config.setCodec('h264');
Config.setCrf(23); // Increased from 18 for faster rendering (still good quality)
Config.setAudioCodec('aac');
Config.setConcurrency(4); // Increased concurrency for faster rendering
