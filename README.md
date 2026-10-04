# Homelab Control

Fundação de um Home Server/HomeLab modular para Kali Linux. A FASE 1 entrega um painel web autenticado, monitoramento do próprio servidor, auditoria e uma base de dados preparada para as próximas fases.

## Arquitetura

```text
Browser -> HTTPS/reverse proxy -> FastAPI
                                  |- Auth/session/CSRF
                                  |- API REST + WebSocket de status
                                  |- Server monitor (psutil)
                                  |- Event/audit service
                                  `- SQLAlchemy -> SQLite (PostgreSQL futuramente)
```

Decisões da FASE 1: FastAPI/Uvicorn, Jinja2 + JavaScript/CSS sem build obrigatório, SQLAlchemy + Alembic, SQLite e psutil. Redis, MQTT, Docker, scanner de rede e bot ficam adiados até existir necessidade concreta.

## Segurança

- Senhas com Argon2id; nunca são armazenadas em texto puro.
- Sessões aleatórias armazenadas como hash no banco, com expiração e revogação.
- CSRF para mutações autenticadas, cookies HttpOnly/SameSite e headers de segurança.
- Rate limit de login em memória na FASE 1; para múltiplos processos, substitua por Redis.
- Nenhum endpoint executa shell. Controle de serviços/dispositivos só será adicionado por adapters e whitelists explícitas.
- Em acesso remoto, prefira Tailscale/WireGuard e mantenha a aplicação atrás de HTTPS. Não exponha Uvicorn diretamente à internet.

## Instalação no Kali Linux

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/create_admin.py
alembic upgrade head
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000/login`. Para serviço permanente, veja `systemd/` e `scripts/install.sh`.

O script `create_admin.py` grava apenas um hash Argon2 em `.env`; ele não grava a senha em arquivo. Em produção, prefira um secret manager ou arquivo de ambiente protegido.

Se o banco já possui um administrador e a senha foi alterada, execute `python scripts/reset_admin.py` para atualizar o hash diretamente no banco.

## API da FASE 1

- `GET /api/health` — health check simples.
- `GET /api/me` — usuário autenticado e permissões.
- `GET /api/server/status` — CPU, RAM, disco, uptime, rede e temperaturas disponíveis.
- `GET /api/events` — auditoria recente.
- `WS /ws/server` — status do servidor a cada 5 segundos, usando a sessão autenticada.

## Próximas fases

1. LAN: inventário manual + descoberta conservadora, ping e histórico.
2. Wake-on-LAN através de adapter e comandos autorizados.
3. Serviços systemd usando whitelist de units, nunca input livre.
4. Câmeras com proxy/conversão RTSP adequada, sem expor RTSP ao browser.
5. Device adapters (MQTT/HTTP/Home Assistant).
6. Discord por worker separado e secrets externos.
7. Event bus/alertas e automações.
8. Acesso remoto endurecido com VPN, HTTPS e MFA.

## Operação exclusivamente local

Esta configuração não usa ngrok, Cloudflare Tunnel, Tailscale, Discord, webhooks ou qualquer endpoint público. Para permitir acesso aos computadores da LAN, configure `BIND_HOST` com o IP fixo do notebook na rede doméstica, por exemplo `192.168.1.50`, e restrinja a porta no firewall à sub-rede local. O dashboard ficará acessível em `http://192.168.1.50:8000`; não use `0.0.0.0` sem firewall.

As páginas `/devices`, `/network`, `/cameras`, `/services`, `/alerts`, `/logs` e `/automation` já estão disponíveis após login. A descoberta de rede lê somente a tabela de vizinhos do sistema operacional e faz ping individual; não há varredura de faixa IP.

### Integrações e limites seguros

- Wake-on-LAN é enviado localmente por broadcast UDP e precisa de MAC cadastrado.
- Serviços systemd só podem ser executados depois de cadastrados na allowlist; o unit name é validado e não existe execução de shell.
- Câmeras podem ser cadastradas e monitoradas como inventário. RTSP não é enviado diretamente ao navegador; um proxy/transcodificador local poderá ser adicionado quando o hardware for conhecido.
- O worker local cria alertas de CPU, RAM, disco e mudança de disponibilidade dos hosts cadastrados.
- MQTT, Home Assistant, Discord e notificações externas permanecem fora desta instalação local. Seus adapters podem ser adicionados sem alterar os modelos centrais.

### Câmera Yoosee local

Para o stream confirmado `192.168.1.57:554/onvif1`, instale Docker/Compose no Kali, copie as variáveis de câmera para `.env` e preencha `CAMERA_RTSP_PASSWORD` com a senha RTSP. Ajuste `BIND_HOST` e as URLs de mídia para o IP LAN do notebook:

```bash
sudo apt install docker.io docker-compose-plugin
sudo systemctl enable --now docker
docker compose up -d mediamtx
```

O proxy lê o RTSP em UDP e publica apenas na interface LAN configurada:

- WebRTC: `http://IP_DO_NOTEBOOK:8889/camera_casa`
- HLS: `http://IP_DO_NOTEBOOK:8888/camera_casa/index.m3u8`

Para WebRTC funcionar entre computadores da LAN, permita também UDP `8189` apenas para a sub-rede doméstica:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8888 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 8889 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 8189 proto udp
```

O arquivo `docker/mediamtx.yml` usa `sourceOnDemand`, então a câmera só é lida enquanto houver um visualizador. O MediaMTX é usado como media router local para converter RTSP em protocolos consumíveis pelo navegador, conforme sua documentação oficial. [MediaMTX — câmeras RTSP](https://mediamtx.org/docs/features/rtsp-cameras-and-servers)

## Como adicionar um dispositivo

Na fase de dispositivos, implemente um adapter em `backend/app/integrations/` seguindo a interface comum, registre capabilities explícitas e persista configuração não sensível no banco. Credenciais devem referenciar variáveis de ambiente/secret store, nunca ser incluídas em payloads ou logs.

## Backup e restauração

`bash scripts/backup.sh` cria um arquivo versionado com o banco e configurações não secretas em `backups/`. O backup exclui `.env`, tokens e credenciais. Para restaurar, pare a aplicação, extraia o banco em `data/` e execute `alembic upgrade head`.

## Docker

Não há Docker obrigatório na FASE 1: um processo Python e SQLite são mais fáceis de manter no notebook. Docker/Podman passa a fazer sentido para PostgreSQL, broker MQTT ou serviços de câmera isolados; cada um deverá ser avaliado pelo acesso a rede/hardware e pelo custo operacional.

## Troubleshooting

- **Não consigo entrar:** confira `ADMIN_USERNAME` e use `python scripts/create_admin.py` para gerar o hash novamente.
- **Métricas sem temperatura:** o hardware/driver pode não expor sensores; o campo fica `null` por design.
- **Cookie não funciona em HTTP:** deixe `SESSION_COOKIE_SECURE=false` apenas em LAN/desenvolvimento. Em produção use HTTPS e `true`.
- **Migração:** execute `alembic upgrade head`; não use `create_all` em produção.
