# database.py
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = "sqlite:///pokemon_fichas.db"
engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    discord_id = Column(String, unique=True)
    nome = Column(String)
    cargo = Column(String)

    fichas = relationship("Ficha", back_populates="usuario")

class Ficha(Base):
    __tablename__ = "fichas"
    id = Column(Integer, primary_key=True)
    nome = Column(String)
    especie = Column(String)
    nivel = Column(Integer)
    moves = Column(Text)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))

    usuario = relationship("Usuario", back_populates="fichas")

Base.metadata.create_all(engine)
session = SessionLocal()
