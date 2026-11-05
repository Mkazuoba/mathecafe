"""SECRET_KEY: sem ela configurada, o servidor usava a chave de exemplo que
esta no codigo publico (quem a conhece forja um login de admin)."""
import pytest

from app.config import resolver_secret_key

FORTE = "k" * 48


def test_chave_de_exemplo_ou_curta_nao_sobe(tmp_path):
    for ruim in ("TROQUE_ESTA_CHAVE_EM_PRODUCAO", "troque_por_uma_chave_aleatoria_longa", "curta123"):
        with pytest.raises(RuntimeError):
            resolver_secret_key(ruim, tmp_path / ".secret_key")
    assert not (tmp_path / ".secret_key").exists()


def test_chave_configurada_e_usada(tmp_path):
    assert resolver_secret_key(f"  {FORTE} ", tmp_path / ".secret_key") == FORTE
    assert not (tmp_path / ".secret_key").exists()


def test_sem_chave_gera_uma_e_reaproveita(tmp_path):
    arquivo = tmp_path / ".secret_key"
    primeira = resolver_secret_key("", arquivo)
    assert len(primeira) >= 48 and arquivo.read_text().strip() == primeira
    # proxima subida usa a mesma: ninguem e deslogado a toa
    assert resolver_secret_key("", arquivo) == primeira
    # arquivo estragado (curto) gera outra
    arquivo.write_text("x")
    assert resolver_secret_key("", arquivo) not in ("x", primeira)


def test_servidor_nao_usa_mais_a_chave_do_codigo():
    from app.config import Settings
    assert Settings.model_fields["SECRET_KEY"].default == ""


# ── Banco do servidor (Configurações → Servidor) ─────────────────────────────

def test_url_do_banco_normalizada():
    from app.config import normalizar_url_banco
    # o Supabase e o Render dão postgres:// ou postgresql://; o driver é o psycopg 3
    assert normalizar_url_banco(" postgres://u:s@h:5432/db ") == "postgresql+psycopg://u:s@h:5432/db"
    assert normalizar_url_banco("postgresql://u:s@h/db") == "postgresql+psycopg://u:s@h/db"
    assert normalizar_url_banco("postgresql+psycopg://u:s@h/db") == "postgresql+psycopg://u:s@h/db"
    assert normalizar_url_banco("sqlite:///./cybercafe.db") == "sqlite:///./cybercafe.db"
    for ruim in ("", "abc", "mysql://u:s@h/db", "http://h/db"):
        with pytest.raises(ValueError):
            normalizar_url_banco(ruim)


def test_descricao_do_banco_esconde_a_senha():
    from app.config import descrever_banco
    d = descrever_banco("postgresql+psycopg://usuario:segredo123@db.exemplo.co:5432/postgres")
    assert d["tipo"] == "PostgreSQL" and "segredo123" not in str(d)
    assert "db.exemplo.co" in d["destino"] and "postgres" in d["destino"]
    assert descrever_banco("sqlite:///./cybercafe.db") == {"tipo": "SQLite", "destino": "./cybercafe.db"}


def test_gravar_no_env_troca_so_a_linha(tmp_path):
    from app.config import gravar_no_env
    env = tmp_path / ".env"
    gravar_no_env(env, "DATABASE_URL", "sqlite:///./a.db")  # arquivo ainda não existe
    assert env.read_text(encoding="utf-8") == "DATABASE_URL=sqlite:///./a.db\n"
    env.write_text("# banco\nDATABASE_URL=sqlite:///./a.db\nSECRET_KEY=abc\n", encoding="utf-8")
    gravar_no_env(env, "DATABASE_URL", "postgresql+psycopg://u:s@h/db")
    assert env.read_text(encoding="utf-8") == "# banco\nDATABASE_URL=postgresql+psycopg://u:s@h/db\nSECRET_KEY=abc\n"
