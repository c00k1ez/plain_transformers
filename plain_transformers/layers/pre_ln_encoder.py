import torch
import torch.nn as nn
import torch.nn.functional as F

from .common_layers import FFN, MultiHeadAttention, TransformerEmbedding, TransformerEncoder
from .utils import create_attention_mask


class PreLNEncoderLayer(nn.Module):
    def __init__(
            self,
            d_model=512,
            n_heads=8,
            dim_feedforward=2048,
            dropout=0.1,
            activation_name="gelu",
            ln_eps=1e-12
        ):
        super(PreLNEncoderLayer, self).__init__()
        self.self_attention = MultiHeadAttention(d_model, n_heads, dropout)
        self.dropout = nn.Dropout(dropout)
        self.ffn = FFN(d_model, dim_feedforward, dropout, activation_name=activation_name)
        self.pre_attn_ln = nn.LayerNorm(d_model, eps=ln_eps)
        self.pre_ffn_ln = nn.LayerNorm(d_model, eps=ln_eps)

    def forward(
            self,
            hidden,
            attention_mask=None,
            get_attention_scores=False
        ):
        attn_scores = None
        block_state = self.pre_attn_ln(hidden)
        block_state = self.self_attention(
            query=block_state,
            key=block_state,
            value=block_state,
            attention_mask=attention_mask,
            get_attention_scores=get_attention_scores
        )
        if get_attention_scores:
            attn_scores = block_state[1]
        block_state = block_state[0]
        block_state = block_state + hidden

        ffn_block_state = self.pre_ffn_ln(block_state)
        ffn_block_state = self.ffn(ffn_block_state)
        ffn_block_state = ffn_block_state + block_state

        output = (ffn_block_state, )
        if get_attention_scores:
            output = output + (attn_scores, )
        return output


# TODO: think about merge matrix for attention
class PreLNTransformerEncoder(nn.Module):
    def __init__(
            self,
            d_model,
            vocab_size,
            max_length,
            pad_token_id,
            token_type_vocab_size,
            dropout,
            n_heads,
            dim_feedforward,
            num_layers,
            use_embedding_layer_norm=False,
            pos_embedding_type='embedding',
            activation_name="gelu",
            ln_eps=1e-12
        ):
        super(PreLNTransformerEncoder, self).__init__()
        self.embedding = TransformerEmbedding(
            vocab_size=vocab_size,
            d_model=d_model,
            max_length=max_length,
            pad_token_id=pad_token_id,
            token_type_vocab_size=token_type_vocab_size,
            pos_embedding_type=pos_embedding_type,
            dropout=dropout,
            use_layer_norm=use_embedding_layer_norm,
            ln_eps=ln_eps
        )
        self.encoder = TransformerEncoder(
            num_layers=num_layers,
            encoder_class=PreLNEncoderLayer,
            d_model=d_model,
            n_heads=n_heads,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            activation_name=activation_name,
            ln_eps=ln_eps
        )

        self.post_encoder_ln = nn.LayerNorm(d_model, eps=ln_eps)

    def forward(
            self,
            input_ids,
            attention_mask=None,
            token_type_ids=None,
            get_attention_scores=False
        ):

        attention_mask = create_attention_mask(
            attention_mask,
            input_ids.shape,
            input_ids.device
        )
        embeddings = self.embedding(input_ids, token_type_ids)
        hidden = self.encoder(
            embeddings,
            attention_mask=attention_mask,
            get_attention_scores=get_attention_scores
        )
        hidden_ln = self.post_encoder_ln(hidden[0])
        output = (hidden_ln, )
        if get_attention_scores:
            output = output + (hidden[1], )
        return output