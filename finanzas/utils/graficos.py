import pandas as pd
import plotly.graph_objects as go
from plotly.offline import plot
from django.db.models.functions import TruncDay
from django.db.models import Sum


def generar_grafico_balance(usuario):
    data = (
        usuario.transaccion_set
        .annotate(dia=TruncDay("fecha"))
        .values("dia")
        .annotate(total=Sum("cantidad"))
        .order_by("dia")
    )

    if data:
        df = pd.DataFrame(data)
        df["dia"] = pd.to_datetime(df["dia"])
    else:
        df = pd.DataFrame({"dia": [], "total": []})

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["dia"],
        y=df["total"],
        mode="lines",
        line=dict(width=3, color="#d4af37"),
        fill="tozeroy",
        fillcolor="rgba(212,175,55,0.15)",
        hovertemplate="%{x|%d-%m-%Y}<br>$%{y:,.0f}<extra></extra>"
    ))

    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=200,
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, zeroline=False, tickformat="%b %d", color="#aaa"),
        yaxis=dict(showgrid=False, zeroline=False, visible=False)
    )

    return plot(fig, output_type="div", include_plotlyjs=False)
