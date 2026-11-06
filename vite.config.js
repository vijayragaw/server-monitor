import {defineConfig} from 'vite';
export default defineConfig({server:{host:'127.0.0.1',proxy:{'/api':{target:'http://127.0.0.1:8081',proxyTimeout:22000,timeout:23000}}}});
