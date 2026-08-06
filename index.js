const { create } = require('@open-wa/wa-automate');

create({
    sessionId: 'whatsapp-session',
    multiDevice: true,
    authTimeout: 60, // Tiempo de espera de autenticación ampliado
    qrTimeout: 0,    // 0 para que el código QR en la terminal no expire rápido
    headless: true,  // Obligatorio en Cloud Shell
    useChrome: true,
    executablePath: '/home/jose_aisasolar/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome',
    throwErrorOnTimeout: false,
    restartOnCrash: async (sessionId) => {
        console.log(`Reiniciando sesión debido a cierre inesperado: ${sessionId}`);
    },
    args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--no-first-run',
        '--no-zygote',
        '--disable-gpu'
    ]
})
.then(client => {
    console.log('¡Cliente de WhatsApp conectado y listo!');
    
    client.onMessage(async message => {
        if (message.body && !message.isGroupMsg) {
            console.log(`Mensaje recibido de ${message.from}: ${message.body}`);
            // Aquí puedes conectar la lógica de respuesta de tu agente
        }
    });
})
.catch(error => {
    console.error('Error crítico al iniciar el cliente:', error);
});
