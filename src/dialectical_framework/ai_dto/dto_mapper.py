from typing import Dict, Generic, Type, TypeVar

from pydantic import BaseModel

from dialectical_framework import DialecticalComponent, Rationale
from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto

# Type variables for generic mapping
DtoType = TypeVar('DtoType', bound=BaseModel)
ModelType = TypeVar('ModelType', bound=BaseModel)


class DtoMapper(Generic[DtoType, ModelType]):
    """
    Generic auto-mapper that uses field introspection to map between DTOs and models.
    Works when models have compatible field names.
    """

    def __init__(self, dto_class: Type[DtoType], model_class: Type[ModelType]):
        self.dto_class = dto_class
        self.model_class = model_class

    def map_from_dto(self, dto: DtoType, **kwargs) -> ModelType:
        """
        Auto-maps from DTO to model using common fields plus any additional kwargs.
        """
        # Get DTO field values
        dto_data = dto.model_dump()

        # Merge with additional kwargs (kwargs take precedence)
        merged_data = {**dto_data, **kwargs}

        # Filter to only include fields that exist in the target model
        model_fields = self.model_class.model_fields.keys()
        filtered_data = {k: v for k, v in merged_data.items() if k in model_fields}

        return self.model_class(**filtered_data)

    def map_list_from_dto(self, dtos: list[DtoType], **kwargs) -> list[ModelType]:
        """
        Maps a list of DTOs to domain models.

        Args:
            dtos: List of DTO instances to convert
            **kwargs: Additional parameters for mapping

        Returns:
            List of domain model instances
        """
        return [self.map_from_dto(dto, **kwargs) for dto in dtos]

class DialecticalComponentMapper(DtoMapper[DialecticalComponentDto, DialecticalComponent]):
    def map_from_dto(self, dto: DialecticalComponentDto, **kwargs) -> ModelType:
        mapped: DialecticalComponent = super().map_from_dto(dto, **kwargs)
        if dto.explanation:
            mapped.rationales.append(Rationale(
                text=dto.explanation,
            ))
        return mapped

# Registry for mappers
_mapper_registry: Dict[tuple[Type, Type], DtoMapper] = {
    # Use default DtoMapper if no specific mapper is registered

    (DialecticalComponentDto, DialecticalComponent): DialecticalComponentMapper(DialecticalComponentDto, DialecticalComponent),
}


def register_mapper(dto_class: Type[DtoType], model_class: Type[ModelType], mapper: DtoMapper[DtoType, ModelType]):
    """
    Register a mapper for a specific DTO-Model pair.
    """
    _mapper_registry[(dto_class, model_class)] = mapper


def get_mapper(dto_class: Type[DtoType], model_class: Type[ModelType]) -> DtoMapper[DtoType, ModelType]:
    """
    Get a mapper for a specific DTO-Model pair.
    If no specific mapper is registered, returns an AutoMapper.
    """
    key = (dto_class, model_class)
    if key in _mapper_registry:
        return _mapper_registry[key]

    # Return auto-mapper as fallback
    return DtoMapper(dto_class, model_class)


def map_from_dto(dto: DtoType, model_class: Type[ModelType], **kwargs) -> ModelType:
    """
    Convenience function to map from DTO to model.
    """
    mapper = get_mapper(type(dto), model_class)
    return mapper.map_from_dto(dto, **kwargs)

def map_list_from_dto(dtos: list[DtoType], model_class: Type[ModelType], **kwargs) -> list[ModelType]:
    """
    Convenience function to map a list of DTOs to domain models.
    """
    if not dtos:
        return []
    mapper = get_mapper(type(dtos[0]), model_class)
    return mapper.map_list_from_dto(dtos, **kwargs)
