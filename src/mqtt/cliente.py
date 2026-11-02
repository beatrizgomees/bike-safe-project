import json
import threading

import paho.mqtt.client as mqtt

from src.mqtt import config, topicos


def codificar(objeto):
    return json.dumps(objeto, ensure_ascii=False, default=str).encode("utf-8")


def decodificar(payload):
    texto = payload.decode("utf-8")

    try:
        return json.loads(texto)
    except ValueError:
        return texto  # ex.: "online" / "offline"


class ClienteMQTT:

    def __init__(self, nome, host=None, porta=None):
        self.nome = nome
        self.host = host or config.BROKER_HOST
        self.porta = porta or config.BROKER_PORT

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"bikesafe-{nome}"
        )
        self.client.max_inflight_messages_set(200)
        self.client.max_queued_messages_set(0)  # sem limite de fila
        self.client.will_set(topicos.status(nome), "offline", qos=1, retain=True)
        self.client.on_connect = self._ao_conectar

        self._conectado = threading.Event()
        self._assinaturas = []   # (filtro, qos)
        self._pendentes = []

    # --------------------------------------------------------------- conexão
    def _ao_conectar(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[{self.nome}] MQTT recusou a conexão: {reason_code}")
            return

        for filtro, qos in self._assinaturas:
            client.subscribe(filtro, qos)

        client.publish(topicos.status(self.nome), "online", qos=1, retain=True)
        self._conectado.set()

    def conectar(self, timeout=15):
        try:
            self.client.connect(self.host, self.porta, keepalive=60)
        except OSError as erro:
            raise RuntimeError(
                f"Não consegui conectar no broker MQTT em {self.host}:{self.porta} ({erro}). "
                f"O Mosquitto está rodando? (docker compose up -d mosquitto)"
            )

        self.client.loop_start()

        if not self._conectado.wait(timeout):
            raise RuntimeError(f"Broker MQTT {self.host}:{self.porta} não respondeu.")

    def desconectar(self):
        info = self.client.publish(topicos.status(self.nome), "offline", qos=1, retain=True)
        info.wait_for_publish(5)
        self.client.disconnect()
        self.client.loop_stop()

    # ----------------------------------------------------------- publicar/assinar
    def publicar(self, topico, objeto, qos=1, retain=False):
        info = self.client.publish(topico, codificar(objeto), qos=qos, retain=retain)
        self._pendentes.append(info)

        return info

    def esperar_envio(self, timeout=60):
        for info in self._pendentes:
            info.wait_for_publish(timeout)

        self._pendentes.clear()

    def assinar(self, filtro, funcao, qos=1):
        def callback(client, userdata, msg):
            funcao(msg.topic, decodificar(msg.payload))

        self.client.message_callback_add(filtro, callback)
        self._assinaturas.append((filtro, qos))

        if self._conectado.is_set():
            self.client.subscribe(filtro, qos)

    def aguardar_online(self, nomes, timeout=90):
        eventos = {}

        for nome in nomes:
            evento = threading.Event()
            eventos[nome] = evento

            self.assinar(
                topicos.status(nome),
                lambda t, p, e=evento: e.set() if p == "online" else e.clear(),
            )

        for nome, evento in eventos.items():
            if not evento.wait(timeout):
                raise RuntimeError(f"O componente '{nome}' não ficou online em {timeout}s.")
