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
